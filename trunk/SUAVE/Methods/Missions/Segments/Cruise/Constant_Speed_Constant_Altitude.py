## @ingroup Methods-Missions-Segments-Cruise
# Constant_Speed_Constant_Altitude.py
# 
# Created:  Jul 2014, SUAVE Team
# Modified: Jan 2016, E. Botero
#           May 2019, T. MacDonald

# ----------------------------------------------------------------------
#  Initialize Conditions
# ----------------------------------------------------------------------

## @ingroup Methods-Missions-Segments-Cruise
def initialize_conditions(segment):
    """Sets the specified conditions which are given for the segment type.

    Assumptions:
    Constant speed and constant altitude
    Wind speed negative for headwind, positive for tailwind

    Source:
    N/A

    Inputs:
    segment.altitude                [meters]
    segment.distance                [meters]
    segment.speed                   [meters/second]
    segment.wind_speed			    [meters/second]

    Outputs:
    conditions.frames.inertial.velocity_vector  [meters/second]
    conditions.frames.inertial.position_vector  [meters]
    conditions.freestream.altitude              [meters]
    conditions.frames.inertial.time             [seconds]
    conditions.frames.wind.wind_velocity_vector [meters/second]

    Properties Used:
    N/A
    """        
    
    # unpack
    alt        = segment.altitude
    xf         = segment.distance
    air_speed  = segment.air_speed
    wind_speed = segment.wind_speed
    conditions = segment.state.conditions 
    
    # check for initial altitude
    if alt is None:
        if not segment.state.initials: raise AttributeError('altitude not set')
        alt = -1.0 * segment.state.initials.conditions.frames.inertial.position_vector[-1,2]
        
    # Assign ground speed
    ground_speed = air_speed + wind_speed
    
    # dimensionalize time
    t_initial = conditions.frames.inertial.time[0,0]
    t_final   = xf / ground_speed + t_initial
    t_nondim  = segment.state.numerics.dimensionless.control_points
    time      = t_nondim * (t_final-t_initial) + t_initial
    
    # pack
    segment.state.conditions.freestream.altitude[:,0]             = alt
    segment.state.conditions.frames.inertial.position_vector[:,2] = -alt # z points down
    segment.state.conditions.frames.inertial.velocity_vector[:,0] = air_speed
    segment.state.conditions.frames.inertial.time[:,0]            = time[:,0]
    segment.state.conditions.frames.wind.wind_velocity_vector[:,0]= wind_speed 
    