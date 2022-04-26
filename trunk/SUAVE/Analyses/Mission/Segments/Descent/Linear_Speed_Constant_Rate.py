## @ingroup Analyses-Mission-Segments-Descent
# Linear_Speed_Constant_Rate.py
#
# Created: Apr 2022, C. Gallagher

# ----------------------------------------------------------------------
#  Imports
# ----------------------------------------------------------------------

# SUAVE imports
from SUAVE.Methods.Missions import Segments as Methods

from .Unknown_Throttle import Unknown_Throttle

# Units
from SUAVE.Core import Units


# ----------------------------------------------------------------------
#  Segment
# ----------------------------------------------------------------------

## @ingroup Analyses-Mission-Segments-Descent
class Linear_Speed_Constant_Rate(Unknown_Throttle):
    """ Linearly change true airspeed while descending at a constant rate.
    
        Assumptions:
        None
        
        Source:
        None
    """       
    
    def __defaults__(self):
        """ This sets the default solver flow. Anything in here can be modified after initializing a segment.
    
            Assumptions:
            None
    
            Source:
            N/A
    
            Inputs:
            None
    
            Outputs:
            None
    
            Properties Used:
            None
        """          
        
        # --------------------------------------------------------------
        #   User inputs
        # --------------------------------------------------------------
        self.altitude_start  = None # Optional
        self.altitude_end    = 0. * Units.km
        self.descent_rate    = 3.  * Units.m / Units.s
        self.air_speed_start = 200 * Units.m / Units.s
        self.air_speed_end   = 100 * Units.m / Units.s
        self.wind_speed      = 0.0 * Units.m / Units.s
        self.true_course     = 0.0 * Units.degrees    
        
        # --------------------------------------------------------------
        #   The Solving Process
        # --------------------------------------------------------------
        initialize = self.process.initialize
        initialize.conditions = Methods.Descent.Linear_Speed_Constant_Rate.initialize_conditions

        

        return
