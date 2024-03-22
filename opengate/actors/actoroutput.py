from ..base import GateObject
from ..image import (
    write_itk_image,
    update_image_py_to_cpp,
    create_3d_image,
    get_py_image_from_cpp_image,
    sum_itk_images,
    divide_itk_images,
)
from ..utility import ensure_filename_is_str, insert_suffix_before_extension
from ..exception import warning, fatal

from pathlib import Path


class DataItemBase:
    _tuple_length = None

    def __init__(self, *args, data=None, **kwargs):
        if data is None:
            data = [None] * self._tuple_length
        self.set_data(data)

    def __add__(self, other):
        return NotImplemented

    def __iadd__(self, other):
        return NotImplemented

    def __truediv__(self, other):
        return NotImplemented

    def write(self, *args, **kwargs):
        raise NotImplementedError(f"This is the base class. ")

    @property
    def data_is_none(self):
        return any([d is None for d in self.data])

    def set_data_items(self, *data_items):
        self.set_data(data_items)

    def set_data(self, data):
        if len(data) != self._tuple_length:
            raise ValueError
        else:
            try:
                self.data = tuple(data)
            except TypeError:
                raise TypeError(
                    f"Incompatible argument data: {data}. Must be an iterable. "
                )

    # def call_method_on_data(self, method_name, *args, **kwargs):
    #     for d in self.data:
    #         getattr(d, method_name)(d, *args, **kwargs)


class SingleDataItem(DataItemBase):

    def __new__(cls, *args, **kwargs):
        cls._tuple_length = 1
        return super(SingleDataItem, cls).__new__(cls)


class MultiDataItem(DataItemBase):
    # _tuple_length = None

    def __new__(cls, tuple_length, *args, **kwargs):
        cls._tuple_length = tuple_length
        return super(MultiDataItem, cls).__new__(cls)

    def __iadd__(self, other):
        self.set_data(
            [self.data[i].__iadd__(other.data[i]) for i in range(self._tuple_length)]
        )
        return self

    def __add__(self, other):
        return type(self)(
            data=[self.data[i] + other.data[i] for i in range(self._tuple_length)]
        )

    def write(self, path):
        for i, d in enumerate(self.data):
            d.write(self.get_output_path_to_item(path, i))  # FIXME use suffix

    def get_output_path_to_item(self, actor_output_path, item):
        """This method is intended to be called from an ActorOutput object which provides the path.
        It returns the amended path to the specific item, e.g. the numerator or denominator in a QuotientDataItem.
        Do not override this method. Rather override get_extra_suffix_for_item()
        """
        return insert_suffix_before_extension(
            actor_output_path, self.get_extra_suffix_for_item(item)
        )

    def get_extra_suffix_for_item(self, item):
        """Override this method in inherited classes to specialize the suffix."""
        try:
            item_as_int = int(item)
        except ValueError:
            item_as_int = None
        if item_as_int is not None and (item_as_int - 1) < self._tuple_length:
            return f"item_{item_as_int}"
        else:
            return None


class DoubleDataItem(MultiDataItem):

    def __new__(cls, *args, **kwargs):
        return super(DoubleDataItem, cls).__new__(cls, 2, *args, **kwargs)


class QuotientDataItem(DoubleDataItem):

    def __init__(self, *args, numerator=None, denominator=None, **kwargs):
        if numerator is not None and denominator is not None:
            kwargs["data"] = (numerator, denominator)
        super().__init__(*args, **kwargs)

    @property
    def numerator(self):
        return self.data[0]

    @property
    def denominator(self):
        return self.data[1]

    @property
    def quotient(self):
        return self.numerator / self.denominator

    def get_extra_suffix_for_item(self, item):
        if item == "quotient":
            return f"quotient"
        elif item in ("numerator", 1):
            return f"numerator"
        elif item in ("denominator", 2):
            return f"denominator"
        else:
            return super().get_extra_suffix_for_item(item)


class SingleItkImageDataItem(SingleDataItem):

    def __init__(self, *args, image=None, **kwargs):
        if image is not None:
            kwargs["data"] = (image,)
        super().__init__(*args, **kwargs)

    @property
    def image(self):
        return self.data[0]

    def __iadd__(self, other):
        if self.data_is_none:
            raise ValueError(
                "This data item does not contain any data yet. "
                "Use set_data() before applying any operations. "
            )
        self.set_data(sum_itk_images([self.image, other.image]))
        return self

    def __add__(self, other):
        if self.data_is_none:
            raise ValueError(
                "This data item does not contain any data yet. "
                "Use set_data() before applying any operations. "
            )
        return type(self)(image=sum_itk_images([self.image, other.image]))

    def __truediv__(self, other):
        if self.data_is_none:
            raise ValueError(
                "This data item does not contain any data yet. "
                "Use set_data() before applying any operations. "
            )
        return type(self)(image=divide_itk_images(self.image, other.image))

    def __itruediv__(self, other):
        if self.data_is_none:
            raise ValueError(
                "This data item does not contain any data yet. "
                "Use set_data() before applying any operations. "
            )
        self.set_data(divide_itk_images(self.image, other.image))
        return self

    def set_image_properties(self, spacing=None, origin=None):
        if not self.data_is_none:
            if spacing is not None:
                self.image.SetSpacing(spacing)
            if origin is not None:
                self.image.SetOrigin(origin)

    def create_empty_image(
        self, size, spacing, pixel_type="float", allocate=True, fill_value=0
    ):
        self.set_data(create_3d_image(size, spacing, pixel_type, allocate, fill_value))

    def write(self, path):
        write_itk_image(self.image, ensure_filename_is_str(path))


class QuotientImageDataItem(QuotientDataItem):

    def __init__(self, *args, numerator_image=None, denominator_image=None, **kwargs):
        if numerator_image is not None:
            kwargs["numerator"] = SingleItkImageDataItem(image=numerator_image)
        if denominator_image is not None:
            kwargs["denominator"] = SingleItkImageDataItem(image=denominator_image)
        super().__init__(*args, **kwargs)

    def set_images(self, numerator_image, denominator_image):
        self.set_data(
            (
                SingleItkImageDataItem(numerator_image),
                SingleItkImageDataItem(denominator_image),
            )
        )

    def create_empty_image(
        self, size, spacing, pixel_type="float", allocate=True, fill_value=0
    ):
        self.numerator.create_empty_image(
            size, spacing, pixel_type, allocate, fill_value
        )
        self.denominator.create_empty_image(
            size, spacing, pixel_type, allocate, fill_value
        )

    def set_image_properties(self, spacing=None, origin=None):
        self.numerator.set_image_properties(spacing, origin)
        self.denominator.set_image_properties(spacing, origin)


data_item_classes = {
    "SingleItkImage": SingleItkImageDataItem,
}


def _setter_hook_belongs_to(self, belongs_to):
    if belongs_to is None:
        fatal("The belongs_to attribute of an ActorOutput cannot be None.")
    try:
        belongs_to_name = belongs_to.name
    except AttributeError:
        belongs_to_name = belongs_to
    return belongs_to_name


def _setter_hook_path(self, path):
    return Path(path)


class ActorOutput(GateObject):
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
            None,
            {
                "doc": "Filename for the data represented by this actor output. "
                "Relative paths and filenames are taken "
                "relative to the global simulation output folder "
                "set via the Simulation.output_path option. ",
            },
        ),
        "write_to_disk": (
            True,
            {
                "doc": "Should the data be written to disk?",
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
        "auto_merge": (
            True,
            {
                "doc": "In case the simulation has multiple runs, should results from separate runs be merged?"
            },
        ),
        "data_item_class": (
            None,
            {"doc": "FIXME"},
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_suffix = ""

        if self.output_filename is None:
            self.output_filename = f"output_{self.name}_from_actor_{self.belongs_to_actor.name}.{self.default_suffix}"

        self.data_per_run = {}  # holds the data per run in memory
        self.merged_data = None  # holds the data merged from multiple runs in memory

    # def __contains__(self, item):
    #     return item in self.data_per_run

    def __len__(self):
        return len(self.data_per_run)

    @property
    def data(self):
        if len(self.data_per_run) > 1:
            warning(
                f"You are using the convenience property 'data' to access the data in this actor output. "
                f"This returns you the data from the first run, but the actor output stores "
                f"data from {len(self.data_per_run)} runs. "
                f"To access them, use 'data_per_run[RUN_INDEX]' instead or 'merged_data'. "
            )
        return self.data_per_run[0]

    @property
    def belongs_to_actor(self):
        return self.simulation.actor_manager.get_actor(self.belongs_to)

    def merge_data(self, list_of_data):
        raise NotImplementedError(
            f"Your are calling this method from the base class {type(self).__name__}, "
            f"but it should be implemented in the specific derived class"
        )

    def merge_data_from_runs(self):
        self.merged_data = self.merge_data(list(self.data_per_run.values()))

    def merge_into_merged_data(self, data):
        self.merged_data = self.merge_data([self.merged_data, data])

    def end_of_run(self, run_index):
        if self.keep_data_per_run is False:
            if self.auto_merge is True:
                self.merge_into_merged_data(self.data_per_run[run_index])
            self.data_per_run[run_index] = None

    def end_of_simulation(self):
        if self.auto_merge is True:
            self.merge_data_from_runs()
        if self.keep_data_per_run is False:
            for k in self.data_per_run:
                self.data_per_run[k] = None

    def store_data(self, data, which):
        if isinstance(data, data_item_classes[self.data_item_class]):
            data_item = data
        else:
            data_item = data_item_classes[self.data_item_class](data=data)
        if which == "merged":
            self.merged_data = data_item
        else:
            try:
                run_index = int(which)  # might be a run_index
                if run_index not in self.data_per_run:
                    self.data_per_run[run_index] = data_item
                else:
                    fatal(
                        f"A data item is already set for run index {run_index}. "
                        f"You can only merge additional data into it. Overwriting is not allowed. "
                    )
            except ValueError:
                fatal(
                    f"Invalid argument 'which' in store_data() method of ActorOutput {self.name}. "
                    f"Allowed values are: 'merged' or a valid run_index. "
                )

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

    def write_data(self, which):
        if which == "all_runs":
            for i, data in self.data_per_run.items():
                if data is not None:
                    data.write(self.get_output_path(i))
        elif which == "merged":
            self.merged_data.write(self.get_output_path(which))
        elif which == "all":
            self.write_data("all_runs")
            self.write_data("merged")
        else:
            try:
                data = self.data_per_run[which]
            except KeyError:
                fatal(
                    f"Invalid argument 'which' in method write_data(): {which}. "
                    f"Allowed values are 'all', 'all_runs', 'merged', or a valid run_index"
                )
            data.write(self.get_output_path(which))

    def write_data_if_requested(self, *args, **kwargs):
        if self.write_to_disk is True:
            self.write_data(*args, **kwargs)

    def get_output_path(self, which):
        full_data_path = self.simulation.get_output_path(self.output_filename)
        if which == "merged":
            return full_data_path.with_name(
                full_data_path.stem + f"_merged" + full_data_path.suffix
            )
        else:
            try:
                run_index = int(which)
            except ValueError:
                fatal(
                    f"Invalid argument 'which' in get_output_path() method "
                    f"of {type(self).__name__} called {self.name}"
                    f"Valid arguments are a run index (int) or the term 'merged'. "
                )
            return full_data_path.with_name(
                full_data_path.stem + f"_run{run_index:04f}" + full_data_path.suffix
            )

    def get_output_path_for_item(self, which, item):
        output_path = self.get_output_path(which)
        if which == "merged":
            data = self.merged_data
        else:
            try:
                data = self.data_per_run[which]
            except KeyError:
                fatal(
                    f"Invalid argument 'which' in method get_output_path_for_item(): {which}. "
                    f"Allowed values are 'merged' or a valid run_index. "
                )
        return data.get_output_path_to_item(output_path, item)

    def close(self):
        if self.keep_data_in_memory is False:
            self.data_per_run = {}
            self.merged_data = None
        super().close()


class ActorOutputImage(ActorOutput):
    user_info_defaults = {
        "merge_method": (
            "sum",
            {
                "doc": "How should images from runs be merged?",
                "allowed_values": ("sum",),
            },
        ),
        "size": (
            None,
            {
                "doc": "Size of the image in voxels.",
            },
        ),
        "spacing": (
            None,
            {
                "doc": "Spacing of the image.",
            },
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_suffix = "mhd"

    # override merge_data() method
    def merge_data(self, list_of_data):
        if self.merge_method == "sum":
            merged_data = list_of_data[0]
            for d in list_of_data[1:]:
                merged_data += d
            return merged_data

    def set_image_properties(self, which, **kwargs):
        for image_data in self.collect_data(which):
            if image_data is not None:
                image_data.set_image_properties(**kwargs)

    def create_empty_image(self, run_index, *args, **kwargs):
        self.data_per_run[run_index].create_empty_image(*args, **kwargs)

    def update_to_cpp_image(self, cpp_image, run_index, copy_data=False):
        update_image_py_to_cpp(
            self.data_per_run[run_index], cpp_image, copy_data=copy_data
        )

    def update_from_cpp_image(self, cpp_image, run_index):
        self.data_per_run[run_index] = get_py_image_from_cpp_image(cpp_image)


class ActorOutputRoot(ActorOutput):
    user_info_defaults = {
        "merge_method": (
            "append",
            {
                "doc": "How should images from runs be merged?",
                "allowed_values": ("append",),
            },
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_suffix = "root"

    def merge_data(self, list_of_data):
        if self.merge_method == "append":
            raise NotImplementedError("Appending ROOT files not yet implemented.")


actor_output_classes = {"root": ActorOutputRoot, "image": ActorOutputImage}
