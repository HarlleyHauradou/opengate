from .SimulationStatisticsActor import *
from .DoseActor import *
from .SourceInfoActor import *
from .PhaseSpaceActor import *
from .TestActor import *
from .HitsCollectionActor import *
from .HitsAdderActor import *
from .HitsEnergyWindowsActor import *

actor_type_names = {SimulationStatisticsActor,
                    DoseActor,
                    SourceInfoActor,
                    PhaseSpaceActor,
                    HitsCollectionActor,
                    HitsAdderActor,
                    HitsEnergyWindowsActor,
                    TestActor}
actor_builders = gam.make_builders(actor_type_names)
