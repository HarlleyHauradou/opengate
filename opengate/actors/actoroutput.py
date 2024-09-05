from pathlib import Path
from copy import deepcopy
from box import Box

from ..base import GateObject
from ..utility import insert_suffix_before_extension, ensure_filename_is_str
from ..exception import warning, fatal
from .dataitems import available_data_container_classes, DataItemContainer


def _setter_hook_belongs_to(self, belongs_to):
    if belongs_to is None:
        fatal("The belongs_to attribute of an ActorOutput cannot be None.")
    try:
        belongs_to_name = belongs_to.name
    except AttributeError:
        belongs_to_name = belongs_to
    return belongs_to_name


def _setter_hook_active(self, active):
    if self.__can_be_deactivated__ is True:
        return bool(active)
    else:
        if bool(active) is not True:
            warning(
                f"The output {self.name} of actor {self.belongs_to_actor.name} cannot be deactivated."
            )
        return True


class ActorOutputBase(GateObject):
    user_info_defaults = {
        "belongs_to": (
            None,
            {
                "doc": "Name of the actor to which this output belongs.",
                "setter_hook": _setter_hook_belongs_to,
                "required": True,
            },
        ),
        "output_filename": (
            "auto",
            {
                "doc": "Filename for the data represented by this actor output. "
                "Relative paths and filenames are taken "
                "relative to the global simulation output folder "
                "set via the Simulation.output_dir option. ",
            },
        ),
        "data_write_config": (
            Box({0: Box({"suffix": None, "write_to_disk": True})}),
            {
                "doc": "Dictionary (Box) to specify which"
                "should be written to disk and how. "
                "The default is picked up from the data container class during instantiation, "
                "and can be changed by the user afterwards. "
            },
        ),
        "keep_data_in_memory": (
            True,
            {
                "doc": "Should the data be kept in memory after the end of the simulation? "
                "Otherwise, it is only stored on disk and needs to be re-loaded manually. "
                "Careful: Large data structures like a phase space need a lot of memory.",
            },
        ),
        "keep_data_per_run": (
            False,
            {
                "doc": "In case the simulation has multiple runs, should separate results per run be kept?"
            },
        ),
        "active": (
            True,
            {
                "doc": "Should this output be calculated by the actor? "
                "Note: Output can be deactivated on in certain actors. ",
                "setter_hook": _setter_hook_active,
            },
        ),
    }

    def __init__(self, *args, active=True, **kwargs):
        super().__init__(*args, **kwargs)

        self.data_per_run = {}  # holds the data per run in memory
        self.merged_data = None  # holds the data merged from multiple runs in memory
        # internal flag which can set by the actor when it creating an actor output
        # via _add_actor_output
        # __can_be_deactivated = False forces the "active" user info to True
        # This is the expected behavior in most digitizers
        # In the DoseActor, on the other hand, users might not want to calculate uncertainty
        self.__can_be_deactivated__ = False
        # self._active = active

    def __len__(self):
        return len(self.data_per_run)

    def __getitem__(self, which):
        return self.get_data(which, None)

    # @property
    # def active(self):
    #     return self._active

    @property
    def write_to_disk(self):
        d = Box([(k, v["write_to_disk"]) for k, v in self.data_write_config.items()])
        if len(d) > 1:
            return d
        elif len(d) == 1:
            return list(d.values())[0]
        else:
            fatal("Nothing defined in data_write_config. ")

    @write_to_disk.setter
    def write_to_disk(self, value):
        self.set_write_to_disk("all", value)

    def set_write_to_disk(self, item, value):
        if item == "all":
            for k in self.data_write_config.keys():
                self.set_write_to_disk(k, value)
        else:
            try:
                self.data_write_config[item]["write_to_disk"] = bool(value)
            except KeyError:
                fatal(
                    f"Unknown item {item}. Known items are {list(self.data_write_config.keys())}."
                )

    @property
    def belongs_to_actor(self):
        return self.simulation.actor_manager.get_actor(self.belongs_to)

    def initialize(self):
        self.initialize_output_filename()

    def initialize_output_filename(self):
        write_to_disk_any = any(
            [v["write_to_disk"] for v in self.data_write_config.values()]
        )
        if (
            self.output_filename == "" or self.output_filename is None
        ) and write_to_disk_any is True:
            fatal(
                f"The actor output {self.name} of actor {self.belongs_to_actor.type_name} has write_to_disk=True, "
                f"but output_filename={self.output_filename}. "
                f"Set output_filename='auto' to let GATE generate it automatically, "
                f"or manually provide an output_filename. "
            )
        elif self.output_filename == "auto":
            self.output_filename = f"{self.name}_from_{self.belongs_to_actor.type_name.lower()}_{self.belongs_to_actor.name}.{self.default_suffix}"

    def write_data_if_requested(self, *args, **kwargs):
        if any([v["write_to_disk"] for v in self.data_write_config.values()]):
            self.write_data(*args, **kwargs)

    def get_output_path(self, which="merged", output_filename=None, **kwargs):
        self.initialize_output_filename()

        if output_filename is None:
            output_filename = self.output_filename
        if isinstance(output_filename, (str, Path)):
            full_data_path = Box({0: self.simulation.get_output_path(output_filename)})
        else:
            full_data_path = Box(
                [
                    (k, self.simulation.get_output_path(v))
                    for k, v in output_filename.items()
                ]
            )

        if which == "merged":
            full_data_path_which = full_data_path
            # return insert_suffix_before_extension(full_data_path, "merged")
        else:
            try:
                run_index = int(which)
            except ValueError:
                fatal(
                    f"Invalid argument 'which' in get_output_path() method "
                    f"of {type(self).__name__} called {self.name}"
                    f"Valid arguments are a run index (int) or the term 'merged'. "
                )
            full_data_path_which = Box(
                [
                    (k, insert_suffix_before_extension(v, f"run{run_index:04f}"))
                    for k, v in full_data_path.items()
                ]
            )

        if len(full_data_path_which) > 1:
            return full_data_path_which
        elif len(full_data_path_which) == 1:
            return list(full_data_path_which.values())[0]
        else:
            return None

    def get_output_path_as_string(self, which="merged", **kwargs):
        return ensure_filename_is_str(self.get_output_path(which=which, **kwargs))

    def close(self):
        if self.keep_data_in_memory is False:
            self.data_per_run = {}
            self.merged_data = None
        super().close()

    def get_data(self, *args, **kwargs):
        raise NotImplementedError("This is the base class. ")

    def store_data(self, *args, **kwargs):
        raise NotImplementedError("This is the base class. ")

    def write_data(self, *args, **kwargs):
        raise NotImplementedError("This is the base class. ")

    def load_data(self, which):
        raise NotImplementedError(
            f"Your are calling this method from the base class {type(self).__name__}, "
            f"but it should be implemented in the specific derived class"
        )


class ActorOutputUsingDataItemContainer(ActorOutputBase):
    user_info_defaults = {
        "merge_method": (
            "sum",
            {
                "doc": "How should images from runs be merged?",
                "allowed_values": ("sum",),
            },
        ),
        "auto_merge": (
            True,
            {
                "doc": "In case the simulation has multiple runs, should results from separate runs be merged?"
            },
        ),
    }

    def __init__(self, data_container_class, *args, **kwargs):

        if type(data_container_class) is type:
            if DataItemContainer not in data_container_class.mro():
                fatal(f"Illegal data container class {data_container_class}. ")
            self.data_container_class = data_container_class
        else:
            try:
                self.data_container_class = available_data_container_classes[
                    data_container_class
                ]
            except KeyError:
                fatal(
                    f"Unknown data item class {data_container_class}. "
                    f"Available classes are: {list(available_data_container_classes.keys())}"
                )
        data_write_config = kwargs.pop("data_write_config", None)
        super().__init__(*args, **kwargs)
        if data_write_config is None:
            # get the default write config from the container class
            self.data_write_config = (
                self.data_container_class.get_default_data_write_config()
            )
        else:
            # set the parameters provided by the user in kwargs
            self.data_write_config = data_write_config

    def get_output_path(self, **kwargs):
        item = kwargs.pop("item", "all")
        if item is None:
            return super().get_output_path(**kwargs)
        else:
            return super().get_output_path(
                output_filename=self.get_output_filename(item=item), **kwargs
            )

    def get_output_filename(self, *args, item="all"):
        if item == "all":
            return Box(
                [
                    (k, self.compose_output_path_to_item(self.output_filename, k))
                    for k in self.data_write_config
                ]
            )
        else:
            return self.compose_output_path_to_item(self.output_filename, item)

    def compose_output_path_to_item(self, output_path, item):
        """This method is intended to be called from an ActorOutput object which provides the path.
        It returns the amended path to the specific item, e.g. the numerator or denominator in a QuotientDataItem.
        Do not override this method.
        """
        return insert_suffix_before_extension(
            output_path, self._get_suffix_for_item(item)
        )
        # else:
        #     return actor_output_path

    def _get_suffix_for_item(self, identifier):
        if identifier in self.data_write_config:
            return self.data_write_config[identifier]["suffix"]
        else:
            fatal(
                f"No data item found with identifier {identifier} "
                f"in container class {self.data_container_class.__name__}. "
                f"Valid identifiers are: {list(self.data_write_config.keys())}."
            )

    def merge_data(self, list_of_data):
        if self.merge_method == "sum":
            merged_data = list_of_data[0]
            for d in list_of_data[1:]:
                merged_data.inplace_merge_with(d)
            return merged_data

    def merge_data_from_runs(self):
        self.merged_data = self.merge_data(list(self.data_per_run.values()))

    def merge_into_merged_data(self, data):
        if self.merged_data is None:
            self.merged_data = data
        else:
            self.merged_data = self.merge_data([self.merged_data, data])

    def end_of_run(self, run_index):
        if self.auto_merge is True:
            self.merge_into_merged_data(self.data_per_run[run_index])
        if self.keep_data_per_run is False:
            self.data_per_run.pop(run_index)

    def end_of_simulation(self):
        self.write_data_if_requested("all")
        # if self.auto_merge is True:
        #     self.merge_data_from_runs()
        # if self.keep_data_per_run is False:
        #     for k in self.data_per_run:
        #         self.data_per_run[k] = None

    def get_data_container(self, which):
        if which == "merged":
            return self.merged_data
        else:
            try:
                run_index = int(which)  # might be a run_index
                if (
                    run_index in self.data_per_run
                    and self.data_per_run[run_index] is not None
                ):
                    return self.data_per_run[run_index]
                else:
                    fatal(f"No data stored for run index {run_index}")
            except ValueError:
                fatal(
                    f"Invalid argument 'which' in get_data() method of ActorOutput {self.name}. "
                    f"Allowed values are: 'merged' or a valid run_index. "
                )

    def get_data(self, which="merged", item=None):
        container = self.get_data_container(which)
        if container is None:
            return None
        else:
            return container.get_data(item)

    def store_data(self, which, *data):
        """data can be either the user data to be wrapped into a DataContainer class or
        an already wrapped DataContainer class.
        """

        if isinstance(data, self.data_container_class):
            data_item = data
            data_item.belongs_to = self
        else:
            data_item = self.data_container_class(belongs_to=self, data=data)
        # FIXME: use store_data if target data exists, otherwise create new container
        if which == "merged":
            self.merged_data = data_item
        else:
            try:
                run_index = int(which)  # might be a run_index
                # if run_index not in self.data_per_run:
                # else:
                #     fatal(
                #         f"A data item is already set for run index {run_index}. "
                #         f"You can only merge additional data into it. Overwriting is not allowed. "
                #     )
            except ValueError:
                fatal(
                    f"Invalid argument 'which' in store_data() method of ActorOutput {self.name}. "
                    f"Allowed values are: 'merged' or a valid run_index. "
                )
            self.data_per_run[run_index] = data_item

    def store_meta_data(self, which, **meta_data):
        """data can be either the user data to be wrapped into a DataContainer class or
        an already wrapped DataContainer class.
        """

        if which == "merged":
            data = self.merged_data
        else:
            try:
                run_index = int(which)  # might be a run_index
            except ValueError:
                fatal(
                    f"Invalid argument 'which' in store_data() method of ActorOutput {self.name}. "
                    f"Allowed values are: 'merged' or a valid run_index. "
                )
            data = self.data_per_run[run_index]
        if data is None:
            fatal(
                f"Cannot store meta data because no data exists yet for which='{which}'."
            )
        data.update_meta_data(meta_data)

    def load_data(self, which):
        raise NotImplementedError(
            f"Your are calling this method from the base class {type(self).__name__}, "
            f"but it should be implemented in the specific derived class"
        )

    def collect_data(self, which, return_identifier=False):
        if which == "merged":
            data = [self.merged_data]
            identifiers = ["merged"]
        elif which == "all_runs":
            data = list(self.data_per_run.values())
            identifiers = list(self.data_per_run.keys())
        elif which == "all":
            data = list(self.data_per_run.values())
            data.append(self.merged_data)
            identifiers = list(self.data_per_run.keys())
            identifiers.append("merged")
        else:
            try:
                ri = int(which)
            except ValueError:
                fatal(f"Invalid argument which in method collect_images(): {which}")
            data = [self.data_per_run[ri]]
            identifiers = [ri]
        if return_identifier is True:
            return data, identifiers
        else:
            return data

    def write_data(self, which, **kwargs):
        if which == "all_runs":
            for k in self.data_per_run.keys():
                self.write_data(k, **kwargs)
        elif which == "merged":
            if self.merged_data is not None:
                # pop out the keyword item which needs to be passed to the write method
                # and which should not be passed to the get_output_path method
                item = kwargs.pop("item", None)
                # the first item=None is needed so that get_output_path returns the path without item-specific suffix
                # the write() method of the data item then handles the suffix
                # depending on the item requested in the second item= kwarg
                self.merged_data.write(
                    self.get_output_path(which=which, item=None, **kwargs), item=item
                )
        elif which == "all":
            self.write_data("all_runs", **kwargs)
            self.write_data("merged", **kwargs)
        else:
            try:
                data = self.data_per_run[which]
            except KeyError:
                fatal(
                    f"Invalid argument 'which' in method write_data(): {which}. "
                    f"Allowed values are 'all', 'all_runs', 'merged', or a valid run_index"
                )
            if data is not None:
                item = kwargs.pop("item", None)
                data.write(self.get_output_path(which, item=None, **kwargs), item=item)


class ActorOutputImage(ActorOutputUsingDataItemContainer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_suffix = "mhd"

    def set_image_properties(self, which, **kwargs):
        for image_data in self.collect_data(which):
            if image_data is not None:
                image_data.set_image_properties(**kwargs)

    def get_image_properties(self, which, item=0):
        if which == "merged":
            if self.merged_data is not None:
                return self.merged_data.get_image_properties()[item]
        else:
            try:
                run_index = int(which)
                try:
                    image_data_container = self.data_per_run[run_index]
                except KeyError:
                    fatal(f"No data found for run index {run_index}.")
                if image_data_container is not None:
                    return image_data_container.get_image_properties()[item]
            except ValueError:
                fatal(
                    f"Illegal argument 'which'. Provide a valid run index or the term 'merged'."
                )

    def create_empty_image(self, run_index, size, spacing, origin=None, **kwargs):
        if run_index not in self.data_per_run:
            self.data_per_run[run_index] = self.data_container_class(belongs_to=self)
        self.data_per_run[run_index].create_empty_image(
            size, spacing, origin=origin, **kwargs
        )


# concrete classes usable in Actors:
class ActorOutputSingleImage(ActorOutputImage):

    def __init__(self, *args, **kwargs):
        super().__init__("SingleItkImage", *args, **kwargs)


class ActorOutputSingleMeanImage(ActorOutputImage):

    def __init__(self, *args, **kwargs):
        super().__init__("SingleMeanItkImage", *args, **kwargs)


class ActorOutputSingleImageWithVariance(ActorOutputImage):

    def __init__(self, *args, **kwargs):
        super().__init__("SingleItkImageWithVariance", *args, **kwargs)


class ActorOutputQuotientImage(ActorOutputImage):

    def __init__(self, *args, **kwargs):
        super().__init__("QuotientItkImage", *args, **kwargs)


class ActorOutputQuotientMeanImage(ActorOutputImage):

    def __init__(self, *args, **kwargs):
        super().__init__("QuotientMeanItkImage", *args, **kwargs)


class ActorOutputRoot(ActorOutputBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_suffix = "root"

    def get_output_path(self, *args, **kwargs):
        return super().get_output_path("merged")

    def initialize(self):
        # for ROOT output, do not set a default output_filename
        # we just DON'T want to dump the file
        if self.output_filename == "" or self.output_filename is None:
            self.write_to_disk = False
        super().initialize()


class ActorOutputCppImage(ActorOutputBase):
    """Simple actor output class to provide the get_output_path() interface
    to actors where the image is entirely handled on the C++-side.

    This actor output does not provide any further functionality and cannot merge data from runs.

    If possible, the actor should be implemented in a way to make use of the ActorOutputImage class.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_suffix = "root"

    def get_output_path(self, *args, **kwargs):
        return super().get_output_path("merged")
