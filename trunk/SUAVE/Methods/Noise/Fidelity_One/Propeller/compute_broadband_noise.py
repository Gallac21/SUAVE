## @ingroup Methods-Noise-Fidelity_One-Propeller
# compute_broadband_noise.py
#
# Created:   Mar 2021, M. Clarke
# Modified:  Feb 2022, M. Clarke

# ----------------------------------------------------------------------
#  Imports
# ----------------------------------------------------------------------
from SUAVE.Core import Data   
import numpy as np  
from SUAVE.Methods.Noise.Fidelity_One.Noise_Tools.dbA_noise                     import A_weighting
from SUAVE.Methods.Noise.Fidelity_One.Noise_Tools.SPL_harmonic_to_third_octave  import SPL_harmonic_to_third_octave  
from SUAVE.Methods.Noise.Fidelity_One.Noise_Tools.SPL_harmonic_to_third_octave  import SPL_harmonic_to_third_octave_old  
from SUAVE.Methods.Noise.Fidelity_One.Noise_Tools.decibel_arithmetic            import SPL_arithmetic
from SUAVE.Methods.Geometry.Two_Dimensional.Cross_Section.Airfoil.compute_naca_4series import compute_naca_4series  
from SUAVE.Methods.Geometry.Two_Dimensional.Cross_Section.Airfoil.import_airfoil_geometry \
     import import_airfoil_geometry
from SUAVE.Methods.Aerodynamics.Airfoil_Panel_Method.airfoil_analysis           import airfoil_analysis
from scipy.special import fresnel

# parallel computing
import multiprocessing 
from functools import partial 
import time 
 
# ----------------------------------------------------------------------
# Frequency Domain Broadband Noise Computation
# ----------------------------------------------------------------------

## @ingroup Methods-Noise-Fidelity_One-Propeller   
def compute_broadband_noise(freestream,angle_of_attack,bspv,
                            velocity_vector,rotors,aeroacoustic_data,settings,broadband_noise_results):
    '''This computes the trailing edge noise compoment of broadband noise of a propeller or 
    lift-rotor in the frequency domain. Boundary layer properties are computed using SUAVE's 
    panel method.
    
    Assumptions:
        Boundary layer thickness (delta) appear to be an order of magnitude off at the trailing edge and 
        correction factor of 0.1 is used. See lines 255 and 256 
        
    Source: 
        Li, Sicheng Kevin, and Seongkyu Lee. "Prediction of Urban Air Mobility Multirotor VTOL Broadband Noise
        Using UCD-QuietFly." Journal of the American Helicopter Society (2021).
    
    Inputs:  
        freestream                                   - freestream data structure                                                          [m/s]
        angle_of_attack                              - aircraft angle of attack                                                           [rad]
        bspv                                         - rotor blade section trailing position edge vectors                                 [m]
        velocity_vector                              - velocity vector of aircraft                                                        [m/s]
        rotors                                       - data structure of rotors                                                           [None] 
        aeroacoustic_data                            - data structure of acoustic data                                                    [None] 
        settings                                     - accoustic settings                                                                 [None] 
        broadband_noise_results                      - results data structure                                                             [None] 
    
    Outputs 
       broadband_noise_results.                       *acoustic data is stored and passed in data structures*                                          
           SPL_prop_broadband_spectrum               - broadband noise in blade passing frequency spectrum                                [dB]
           SPL_prop_broadband_spectrum_dBA           - dBA-Weighted broadband noise in blade passing frequency spectrum                   [dbA]     
           SPL_prop_broadband_1_3_spectrum           - broadband noise in 1/3 octave spectrum                                             [dB]
           SPL_prop_broadband_1_3_spectrum_dBA       - dBA-Weighted broadband noise in 1/3 octave spectrum                                [dBA]                               
           azimuthal_broadband_pressure                - azimuthal varying pressure ratio of broadband noise                                [Unitless]       
           azimuthal_broadband_pressure_dBA            - azimuthal varying pressure ratio of dBA-weighted broadband noise                   [Unitless]     
           azimuthal_broadband_spectrum_SPL     - azimuthal varying broadband noise in blade passing frequency spectrum              [dB]      
           azimuthal_broadband_spectrum_SPL_dBA - azimuthal varying dBA-Weighted broadband noise in blade passing frequency spectrum [dbA]   
        
    Properties Used:
        N/A   
    '''     

    num_processors = settings.number_of_multiprocessing_workers 
    parallel_computing_flag_1 = False
    parallel_computing_flag_2 = True
    
    num_cpt        = len(angle_of_attack)
    num_rot        = len(bspv.blade_section_coordinate_sys[0,0,:,0,0,0,0,0])
    num_mic        = len(bspv.blade_section_coordinate_sys[0,:,0,0,0,0,0,0])  
    rotor          = rotors[list(rotors.keys())[0]]
    frequency      = settings.center_frequencies
    num_cf         = len(frequency)     
    
    # ----------------------------------------------------------------------------------
    # Trailing Edge Noise
    # ---------------------------------------------------------------------------------- 
    p_ref              = 2E-5                               # referece atmospheric pressure
    c_0                = freestream.speed_of_sound          # speed of sound
    rho                = freestream.density                 # air density 
    dyna_visc          = freestream.dynamic_viscosity
    kine_visc          = dyna_visc/rho                      # kinematic viscousity    
    alpha_blade        = aeroacoustic_data.disc_effective_angle_of_attack 
    Vt_2d              = aeroacoustic_data.disc_tangential_velocity  
    Va_2d              = aeroacoustic_data.disc_axial_velocity                
    blade_chords       = rotor.chord_distribution           # blade chord    
    r                  = rotor.radius_distribution          # radial location   
    num_sec            = len(r) 
    num_azi            = len(aeroacoustic_data.disc_effective_angle_of_attack[0,0,:])   
    U_blade            = np.sqrt(Vt_2d**2 + Va_2d**2)
    Re_blade           = U_blade*np.repeat(np.repeat(blade_chords[np.newaxis,:],num_cpt,axis=0)[:,:,np.newaxis],num_azi,axis=2)*\
                          np.repeat(np.repeat((rho/dyna_visc),num_sec,axis=1)[:,:,np.newaxis],num_azi,axis=2)
    rho_blade          = np.repeat(np.repeat(rho,num_sec,axis=1)[:,:,np.newaxis],num_azi,axis=2)
    U_inf              = np.atleast_2d(np.linalg.norm(velocity_vector,axis=1)).T
    M                  = U_inf/c_0                                             
    B                  = rotor.number_of_blades             # number of rotor blades
    Omega              = aeroacoustic_data.omega            # angular velocity   
    beta_sq            = 1 - M**2                                  
    delta_r            = np.zeros_like(r)
    del_r              = r[1:] - r[:-1]
    delta_r[0]         = 2*del_r[0]
    delta_r[-1]        = 2*del_r[-1]
    delta_r[1:-1]      = (del_r[:-1]+ del_r[1:])/2


    broadband_noise_results.p_pref_broadband                          = np.zeros((num_cpt,num_mic,num_rot,num_cf)) 
    broadband_noise_results.p_pref_broadband_dBA                      = np.zeros((num_cpt,num_mic,num_rot,num_cf)) 
    broadband_noise_results.SPL_prop_broadband_spectrum               = np.zeros_like(broadband_noise_results.p_pref_broadband)
    broadband_noise_results.SPL_prop_broadband_spectrum_dBA           = np.zeros_like(broadband_noise_results.p_pref_broadband)
    broadband_noise_results.SPL_prop_broadband_1_3_spectrum           = np.zeros((num_cpt,num_mic,num_rot,num_cf))
    broadband_noise_results.SPL_prop_broadband_1_3_spectrum_dBA       = np.zeros((num_cpt,num_mic,num_rot,num_cf))
    broadband_noise_results.azimuthal_broadband_pressure                = np.zeros((num_cpt,num_mic,num_rot,num_azi,num_cf))
    broadband_noise_results.azimuthal_broadband_pressure_dBA            = np.zeros_like(broadband_noise_results.azimuthal_broadband_pressure)
    broadband_noise_results.azimuthal_broadband_spectrum_SPL     = np.zeros_like(broadband_noise_results.azimuthal_broadband_pressure)
    broadband_noise_results.azimuthal_broadband_spectrum_SPL_dBA = np.zeros_like(broadband_noise_results.azimuthal_broadband_pressure)
    
    if np.all(Omega == 0):
        pass  
    else: 
        ti1 = time.time() 
        delta        = np.zeros((num_cpt,num_mic,num_rot,num_sec,num_azi,num_cf,2)) #  control points ,  number rotors, number blades , number sections , sides of airfoil
        delta_star   = np.zeros_like(delta)
        dp_dx        = np.zeros_like(delta)
        tau_w        = np.zeros_like(delta)
        Ue           = np.zeros_like(delta)
        Theta        = np.zeros_like(delta)  
        
        lower_surface_theta      = np.zeros((num_cpt,num_sec,num_azi))
        lower_surface_delta      = np.zeros_like(lower_surface_theta)
        lower_surface_delta_star = np.zeros_like(lower_surface_theta)
        lower_surface_cf         = np.zeros_like(lower_surface_theta)
        lower_surface_Ue         = np.zeros_like(lower_surface_theta)
        lower_surface_H          = np.zeros_like(lower_surface_theta)
        lower_surface_dp_dx      = np.zeros_like(lower_surface_theta)
        upper_surface_theta      = np.zeros_like(lower_surface_theta)
        upper_surface_delta      = np.zeros_like(lower_surface_theta)
        upper_surface_delta_star = np.zeros_like(lower_surface_theta)
        upper_surface_cf         = np.zeros_like(lower_surface_theta)
        upper_surface_Ue         = np.zeros_like(lower_surface_theta)
        upper_surface_H          = np.zeros_like(lower_surface_theta)
        upper_surface_dp_dx      = np.zeros_like(lower_surface_theta)
    
        # ------------------------------------------------------------
        # ****** TRAILING EDGE BOUNDARY LAYER PROPERTY CALCULATIONS  ****** 
        TE_idx  =  4  # assume trailing edge is the forth from last panel

        if rotor.nonuniform_freestream: 
            for i_azi in range(num_azi):
                Re_batch                = np.atleast_2d(Re_blade[cp_i,:,i_azi]).T
                AoA_batch               = np.atleast_2d(alpha_blade[cp_i,:,i_azi]).T
                if rotor.airfoil_flag  == True:
                    a_geo                   = rotor.airfoil_geometry
                    airfoil_data            = import_airfoil_geometry(a_geo, npoints = rotor.number_of_airfoil_section_points)
                    npanel                  = len(airfoil_data.x_coordinates[0]) - 2 
                    pool   = multiprocessing.Pool(processes= num_processors)  
                    data_list = list(np.arange(num_cpt))        
                    prod_x = partial(compute_rotor_section_boundary_layers,default_airfoil_data,AoA_batch,Re_batch,npanel,default_airfoil_polar_stations) 
                    AP = pool.map(prod_x, data_list)  
                else:
                    camber                          = 0.0
                    camber_loc                      = 0.0
                    thickness                       = 0.12
                    default_airfoil_data            = compute_naca_4series(camber, camber_loc, thickness,(rotor.number_of_airfoil_section_points*2 - 2))
                    airfoil_polar_stations          = np.zeros(num_sec)
                    default_airfoil_polar_stations  = list(airfoil_polar_stations.astype(int) ) 
                    npanel                          = len(default_airfoil_data.x_coordinates[0]) - 2
    
                    pool   = multiprocessing.Pool(processes= num_processors)  
                    data_list = list(np.arange(num_cpt))        
                    prod_x = partial(compute_rotor_section_boundary_layers,default_airfoil_data,AoA_batch,Re_batch,npanel,default_airfoil_polar_stations) 
                    AP = pool.map(prod_x, data_list)  
                    
                for cp_i in range(num_cpt):
                    # extract properties
                    lower_surface_theta[cp_i,:,i_azi]      = AP[cp_i].theta[:,TE_idx]
                    lower_surface_delta[cp_i,:,i_azi]      = AP[cp_i].delta[:,TE_idx]
                    lower_surface_delta_star[cp_i,:,i_azi] = AP[cp_i].delta_star[:,TE_idx]
                    lower_surface_cf[cp_i,:,i_azi]         = AP[cp_i].Cf[:,TE_idx]
                    lower_surface_Ue[cp_i,:,i_azi]         = AP[cp_i].Ue_Vinf[:,TE_idx]*U_blade[cp_i,:,i_azi]
                    lower_surface_H[cp_i,:,i_azi]          = AP[cp_i].H[:,TE_idx]
                    surface_dcp_dx                         = (np.diff(AP[cp_i].Cp,axis = 1)/np.diff(AP[cp_i].x,axis = 1))
                    lower_surface_dp_dx[cp_i,:,i_azi]      = abs(surface_dcp_dx[:,TE_idx]*(0.5*rho_blade[cp_i,:,i_azi]*U_blade[cp_i,:,i_azi]**2)/blade_chords)
                    upper_surface_theta[cp_i,:,i_azi]      = AP[cp_i].theta[:,-TE_idx]
                    upper_surface_delta[cp_i,:,i_azi]      = AP[cp_i].delta[:,-TE_idx]
                    upper_surface_delta_star[:,i_azi]      = AP[cp_i].delta_star[:,-TE_idx]
                    upper_surface_cf[cp_i,:,i_azi]         = AP[cp_i].Cf[:,-TE_idx]
                    upper_surface_Ue[cp_i,:,i_azi]         = AP[cp_i].Ue_Vinf[:,-TE_idx]*U_blade[cp_i,:,i_azi]
                    upper_surface_H[cp_i,:,i_azi]          = AP[cp_i].H[:,-TE_idx]
                    upper_surface_dp_dx[cp_i,:,i_azi]      = abs(surface_dcp_dx[:,-TE_idx]*(0.5*rho_blade[cp_i,:,i_azi]*U_blade[cp_i,:,i_azi]**2)/blade_chords)
        else: 
            if rotor.airfoil_flag  == True:
                a_geo                   = rotor.airfoil_geometry
                airfoil_data            = import_airfoil_geometry(a_geo, npoints = rotor.number_of_airfoil_section_points) 
                npanel                  = len(airfoil_data.x_coordinates[0]) - 2
                
                pool   = multiprocessing.Pool(processes= num_processors)  
                data_list = list(np.arange(num_cpt))        
                prod_x = partial(compute_rotor_section_boundary_layers,
                                 airfoil_data =  airfoil_data,
                                 alpha_blade = alpha_blade,
                                 Re_blade = Re_blade,
                                 npanel = npanel,
                                 airfoil_polar_stations = rotor.airfoil_polar_stations ) 
                AP = pool.map(prod_x, data_list)  
            
            else:
                camber                          = 0.0
                camber_loc                      = 0.0
                thickness                       = 0.12
                default_airfoil_data            = compute_naca_4series(camber, camber_loc, thickness,(rotor.number_of_airfoil_section_points*2 - 2))
                airfoil_polar_stations          = np.zeros(num_sec)
                default_airfoil_polar_stations  = list(airfoil_polar_stations.astype(int) ) 
                npanel                          = len(default_airfoil_data.x_coordinates[0]) - 2
                
                pool   = multiprocessing.Pool(processes= num_processors)  
                data_list = list(np.arange(num_cpt))        
                prod_x = partial(compute_rotor_section_boundary_layers,
                                 airfoil_data =  default_airfoil_data,
                                 AoA_batch = AoA_batch,
                                 Re_batch = Re_batch,
                                 npanel = npanel,
                                 airfoil_polar_stations = default_airfoil_polar_stations) 
                AP = pool.map(prod_x, data_list)  
    
            for cp_i in range(num_cpt):
                # extract properties
                surface_dcp_dx                     = (np.diff(AP[cp_i].Cp,axis = 1)/np.diff(AP[cp_i].x,axis = 1))
                lower_surface_theta[cp_i,:,:]      = np.tile(AP[cp_i].theta[:,TE_idx][:,None],(1,num_azi))
                lower_surface_delta[cp_i,:,:]      = np.tile(AP[cp_i].delta[:,TE_idx][:,None],(1,num_azi))*0.1
                lower_surface_delta_star[cp_i,:,:] = np.tile(AP[cp_i].delta_star[:,TE_idx][:,None],(1,num_azi))
                lower_surface_cf[cp_i,:,:]         = np.tile(AP[cp_i].Cf[:,TE_idx][:,None],(1,num_azi))
                lower_surface_Ue[cp_i,:,:]         = np.tile((AP[cp_i].Ue_Vinf[:,TE_idx]*U_blade[cp_i,:,0])[:,None],(1,num_azi))
                lower_surface_H[cp_i,:,:]          = np.tile(AP[cp_i].H[:,TE_idx][:,None],(1,num_azi))
                lower_surface_dp_dx[cp_i,:,:]      = np.tile((surface_dcp_dx[:,TE_idx]*(0.5*rho_blade[cp_i,:,0]*(U_blade[cp_i,:,0]**2))/blade_chords)[:,None],(1,num_azi))
                upper_surface_theta[cp_i,:,:]      = np.tile(AP[cp_i].theta[:,-TE_idx][:,None],(1,num_azi))
                upper_surface_delta[cp_i,:,:]      = np.tile(AP[cp_i].delta[:,-TE_idx][:,None],(1,num_azi))*0.1
                upper_surface_delta_star[cp_i,:,:] = np.tile(AP[cp_i].delta_star[:,-TE_idx][:,None],(1,num_azi))
                upper_surface_cf[cp_i,:,:]         = np.tile(AP[cp_i].Cf[:,-TE_idx][:,None],(1,num_azi))
                upper_surface_Ue[cp_i,:,:]         = np.tile((AP[cp_i].Ue_Vinf[:,-TE_idx]*U_blade[cp_i,:,0])[:,None],(1,num_azi))
                upper_surface_H[cp_i,:,:]          = np.tile(AP[cp_i].H[:,-TE_idx][:,None],(1,num_azi))
                upper_surface_dp_dx[cp_i,:,:]      = np.tile((surface_dcp_dx[:,-TE_idx]*(0.5*rho_blade[cp_i,:,0]*(U_blade[cp_i,:,0]**2))/blade_chords)[:,None],(1,num_azi))
         
            
        # replace nans 0 with mean as a post post-processor
        lower_surface_theta       = np.nan_to_num(lower_surface_theta)
        upper_surface_theta       = np.nan_to_num(upper_surface_theta)
        lower_surface_delta       = np.nan_to_num(lower_surface_delta)
        upper_surface_delta       = np.nan_to_num(upper_surface_delta)
        lower_surface_delta_star  = np.nan_to_num(lower_surface_delta_star)
        upper_surface_delta_star  = np.nan_to_num(upper_surface_delta_star)
        lower_surface_cf          = np.nan_to_num(lower_surface_cf)
        upper_surface_cf          = np.nan_to_num(upper_surface_cf)
        lower_surface_dp_dx       = np.nan_to_num(lower_surface_dp_dx )
        upper_surface_dp_dx       = np.nan_to_num(upper_surface_dp_dx )
        lower_surface_Ue          = np.nan_to_num(lower_surface_Ue)
        upper_surface_Ue          = np.nan_to_num(upper_surface_Ue)
        lower_surface_H           = np.nan_to_num(lower_surface_H)
        upper_surface_H           = np.nan_to_num(upper_surface_H)

        # apply thresholds for non-converged boundary layer solutions form pandel code 
        lower_surface_theta[abs(lower_surface_theta)> 0.01 ]           = 0.0
        upper_surface_theta[abs(upper_surface_theta)>0.01 ]            = 0.0
        lower_surface_delta[abs(lower_surface_delta)> 0.1 ]            = 0.0
        upper_surface_delta[abs(upper_surface_delta)> 0.1]             = 0.0
        lower_surface_delta_star[abs(lower_surface_delta_star)>0.1 ]   = 0.0
        upper_surface_delta_star[abs(upper_surface_delta_star)>0.1 ]   = 0.0
        lower_surface_cf[abs(lower_surface_cf)>0.1 ]                   = 0.0
        upper_surface_cf[abs(upper_surface_cf)> 0.1]                   = 0.0
        lower_surface_dp_dx[abs(lower_surface_dp_dx)> 1E7]             = 0.0
        upper_surface_dp_dx[abs(upper_surface_dp_dx)> 1E7]             = 0.0
        lower_surface_Ue[abs(lower_surface_Ue)> 500.]                  = 0.0
        upper_surface_Ue[abs(upper_surface_Ue)> 500.]                  = 0.0
        lower_surface_H[abs(lower_surface_H)> 10.]                     = 0.0
        upper_surface_H[abs(upper_surface_H)> 10.]                     = 0.0 

        # replace null solutions with mean
        lower_surface_theta[lower_surface_theta == 0]           = np.mean(lower_surface_theta)
        upper_surface_theta[upper_surface_theta == 0]           = np.mean(upper_surface_theta)
        lower_surface_delta[lower_surface_delta == 0]           = np.mean(lower_surface_delta)
        upper_surface_delta[upper_surface_delta == 0]           = np.mean(upper_surface_delta)
        lower_surface_delta_star[lower_surface_delta_star == 0] = np.mean(lower_surface_delta_star)
        upper_surface_delta_star[upper_surface_delta_star== 0]  = np.mean(upper_surface_delta_star)
        lower_surface_cf[lower_surface_cf == 0]                 = np.mean(lower_surface_cf)
        upper_surface_cf[upper_surface_cf == 0]                 = np.mean(upper_surface_cf)
        lower_surface_dp_dx [lower_surface_dp_dx  == 0]         = np.mean(lower_surface_dp_dx )
        upper_surface_dp_dx [upper_surface_dp_dx  == 0]         = np.mean(upper_surface_dp_dx )
        lower_surface_Ue[lower_surface_Ue == 0]                 = np.mean(lower_surface_Ue)
        upper_surface_Ue[upper_surface_Ue == 0]                 = np.mean(upper_surface_Ue)
        lower_surface_H[lower_surface_H == 0]                   = np.mean(lower_surface_H)
        upper_surface_H[upper_surface_H == 0]                   = np.mean(upper_surface_H)

        # ------------------------------------------------------------
        # ****** TRAILING EDGE BOUNDARY LAYER PROPERTY CALCULATIONS  ******

        delta[:,:,:,:,:,:,0]        = np.tile(lower_surface_delta[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # lower surface boundary layer thickness
        delta[:,:,:,:,:,:,1]        = np.tile(upper_surface_delta[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # upper surface boundary layer thickness
        delta_star[:,:,:,:,:,:,0]   = np.tile(lower_surface_delta_star[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf)) # lower surface displacement thickness
        delta_star[:,:,:,:,:,:,1]   = np.tile(upper_surface_delta_star[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf)) # upper surface displacement thickness
        dp_dx[:,:,:,:,:,:,0]        = np.tile(lower_surface_dp_dx[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # lower surface pressure differential
        dp_dx[:,:,:,:,:,:,1]        = np.tile(upper_surface_dp_dx[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # upper surface pressure differential
        Ue[:,:,:,:,:,:,0]           = np.tile(lower_surface_Ue[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))         # lower surface boundary layer edge velocity
        Ue[:,:,:,:,:,:,1]           = np.tile(upper_surface_Ue[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))         # upper surface boundary layer edge velocity
        tau_w[:,:,:,:,:,:,0]        = np.tile((lower_surface_cf*(0.5*rho_blade*(U_blade**2)))[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))       # lower surface wall shear stress
        tau_w[::,:,:,:,:,:,1]       = np.tile((upper_surface_cf*(0.5*rho_blade*(U_blade**2)))[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # upper surface wall shear stress
        Theta[:,:,:,:,:,:,0]        = np.tile(lower_surface_theta[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # lower surface momentum thickness
        Theta[:,:,:,:,:,:,1]        = np.tile(upper_surface_theta[:,None,None,:,:,None],(1,num_mic,num_rot,1,1,num_cf))      # upper surface momentum thickness      
                
        # Update dimensions for computation
        r         = np.tile(r[None,None,None,:,None,None],(num_cpt,num_mic,num_rot,1,num_azi,num_cf))
        c         = np.tile(blade_chords[None,None,None,:,None,None],(num_cpt,num_mic,num_rot,1,num_azi,num_cf))
        delta_r   = np.tile(delta_r[None,None,None,:,None,None],(num_cpt,num_mic,num_rot,1,num_azi,num_cf))
        M         = np.tile(M[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,1))  
        c_0       = np.tile(c_0[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,2))
        beta_sq   = np.tile(beta_sq[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,2))
        Omega     = np.tile(Omega[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,2))
        U_inf     = np.tile(U_inf[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,2))
        rho       = np.tile(rho[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,2))
        kine_visc = np.tile(kine_visc[:,None,None,None,None,None,:],(1,num_mic,num_rot,num_sec,num_azi,num_cf,2))

        X   = np.tile(bspv.blade_section_coordinate_sys[:,:,:,:,:,:,0,:],(1,1,1,1,1,1,2))
        Y   = np.tile(bspv.blade_section_coordinate_sys[:,:,:,:,:,:,1,:],(1,1,1,1,1,1,2))
        Z   = np.tile(bspv.blade_section_coordinate_sys[:,:,:,:,:,:,2,:],(1,1,1,1,1,1,2)) 
        
        # ------------------------------------------------------------
        # ****** BLADE MOTION CALCULATIONS ******
        # the rotational Mach number of the blade section
        omega   = np.tile((2*np.pi*frequency)[None,None,None,None,None,:,None],(num_cpt,num_mic,num_rot,num_sec,num_azi,1,2))
        r       = np.tile(r[:,:,:,:,:,:,None],(1,1,1,1,1,1,2))
        c       = np.tile(c[:,:,:,:,:,:,None],(1,1,1,1,1,1,2))/2
        delta_r = np.tile(delta_r[:,:,:,:,:,:,None],(1,1,1,1,1,1,2))
        M       = np.tile(M,(1,1,1,1,1,1,2))
        R_s     = np.tile(np.linalg.norm(bspv.blade_section_coordinate_sys,axis = 6),(1,1,1,1,1,1,2))
        mu      = (omega/(1 +(Omega*r/c_0)*(X/R_s)))*M/(U_inf*beta_sq)

        # ------------------------------------------------------------
        # ****** LOADING TERM CALCULATIONS ******
        # equation 7
        epsilon       = X**2 + (beta_sq)*(Y**2 + Z**2)
        gamma         = np.sqrt(((mu/epsilon)**2)*(X**2 + beta_sq*(Z**2)))
        ss_1, cc_1    = fresnel(2*((((omega/(1 +  (Omega*r/c_0)*(X/R_s))) /(0.8*U_inf)) /c) + (mu/c)*M + (gamma/c)))
        ss_2, cc_2    = fresnel(2*((mu/c)*X/epsilon + (gamma/c)) )
        triangle      = (omega/(U_inf*c)) - (mu/c)*X/epsilon + (mu/c)*M
        norm_L_sq     = (1/triangle)*abs(np.exp(1j*2*triangle)*((1 - (1 + 1j)*(cc_1 - 1j*ss_1)) \
                        + ((np.exp(-1j*2*triangle))*(np.sqrt((((omega/(1 +  (Omega*r/c_0)*(X/R_s))) /(0.8*U_inf)) + mu*M + gamma)/(mu*X/epsilon +gamma))) \
                           *(1 + 1j)*(cc_2 - 1j*ss_2)) ))
        norm_L_sq     = np.nan_to_num(norm_L_sq) 
        
        # ------------------------------------------------------------
        # ****** EMPIRICAL WALL PRESSURE SPECTRUM ******
        ones                     = np.ones_like(Theta)
        beta_c                   = (Theta/tau_w)*dp_dx 
        d                        = 4.76*((1.4/(delta/delta_star))**0.75)*(0.375*(3.7 + 1.5*beta_c) - 1)
        a                        = (2.82*((delta/delta_star)**2)*(np.power((6.13*((delta/delta_star)**(-0.75)) + d),(3.7 + 1.5*beta_c))))*\
                                   (4.2*((0.8*((beta_c + 0.5)**3/4))/(delta/delta_star)) + 1)
        d_star                   = d
        d_star[beta_c<0.5]       = np.maximum(ones,1.5*d)[beta_c<0.5]
        Phi_pp_expression        =  (np.maximum(a, (0.25*beta_c - 0.52)*a)*((omega*delta_star/Ue)**2))/(((4.76*((omega*delta_star/Ue)**0.75) \
                                    + d_star)**(3.7 + 1.5*beta_c))+ (np.power((8.8*(((delta/Ue)/(kine_visc/(((tau_w/rho)**0.5)**2)))**(-0.57))\
                                    *(omega*delta_star/Ue)),(np.minimum(3*ones,(0.139 + 3.1043*beta_c)) + 7)) ))
        Phi_pp                   = ((tau_w**2)*delta_star*Phi_pp_expression)/Ue
        Phi_pp[np.isinf(Phi_pp)] = 0.
        Phi_pp[np.isnan(Phi_pp)] = 0. 
        
        # Power Spectral Density from each blade
        mult       = ((omega/c_0)**2)*(c**2)*delta_r*(1/(32*np.pi**2))*(B/(2*np.pi))
        int_x      = np.linspace(0,2*np.pi,num_azi)  
        S_pp_azi   = mult*((Z/(X**2 + (1-M**2)*(Y**2 + Z**2)))**2)*norm_L_sq*\
                                                  (1.6*(0.8*U_inf)/omega)*Phi_pp  
        S_pp_azi[np.isinf(S_pp_azi)] = 0   
        S_pp       = np.trapz(S_pp_azi,x = int_x,axis = 4)  
        
        # Sound Pressure Level
        SPL                          = 10*np.log10((2*np.pi*abs(S_pp))/((p_ref)**2)) 
        SPL_azi                      = 10*np.log10((2*np.pi*S_pp_azi)/((p_ref)**2))
        SPL_surf                     = SPL_arithmetic(SPL, sum_axis = 5 )     
        SPL_rotor                    = SPL_arithmetic(SPL_surf, sum_axis = 3 )   
        SPL_rotor_dBA                = A_weighting(SPL_rotor,frequency)
        SPL_surf_azi                 = SPL_arithmetic(SPL_azi, sum_axis = 6 ) 
        SPL_rotor_azi                = SPL_arithmetic(SPL_surf_azi, sum_axis = 3 ) 
        SPL_rotor_dBA_azi            = A_weighting(SPL_rotor_azi,frequency)  
        
        # convert to 1/3 octave spectrum
        f = np.repeat(np.atleast_2d(frequency),num_cpt,axis = 0) 
        
        broadband_noise_results.p_pref_broadband                              = 10**(SPL_rotor /10) 
        broadband_noise_results.p_pref_broadband_dBA                          = 10**(SPL_rotor_dBA /10)   
        broadband_noise_results.SPL_prop_broadband_spectrum                   = SPL_rotor
        broadband_noise_results.SPL_prop_broadband_spectrum_dBA               = A_weighting(SPL_rotor,frequency) 
        broadband_noise_results.SPL_prop_broadband_1_3_spectrum               = SPL_harmonic_to_third_octave_old(SPL_rotor,f,settings)  
        broadband_noise_results.SPL_prop_broadband_1_3_spectrum_dBA           = SPL_harmonic_to_third_octave_old(SPL_rotor_dBA,f,settings)   
        broadband_noise_results.azimuthal_broadband_pressure                  = 10**(SPL_rotor_azi /10)   
        broadband_noise_results.azimuthal_broadband_pressure_dBA              = 10**(SPL_rotor_dBA_azi /10)  
        broadband_noise_results.azimuthal_broadband_spectrum_SPL              = SPL_rotor_azi  
        broadband_noise_results.azimuthal_broadband_spectrum_SPL_dBA          = SPL_rotor_dBA_azi       
             
    return


#def compute_mic_broadband(i,freestream,angle_of_attack,bspv,velocity_vector,rotors,aeroacoustic_data,settings,BL_Data):
   
    #num_cpt        = len(angle_of_attack)
    #num_rot        = len(bspv.blade_section_coordinate_sys[0,0,:,0,0,0,0,0]) 
    #rotor          = rotors[list(rotors.keys())[0]]
    #frequency      = settings.center_frequencies
    #num_cf         = len(frequency)     
    
    ## ----------------------------------------------------------------------------------
    ## Trailing Edge Noise
    ## ---------------------------------------------------------------------------------- 
    #p_ref              = 2E-5                               # referece atmospheric pressure
    #c_0                = freestream.speed_of_sound          # speed of sound
    #rho                = freestream.density                 # air density 
    #dyna_visc          = freestream.dynamic_viscosity
    #kine_visc          = dyna_visc/rho                      # kinematic viscousity        
    #blade_chords       = rotor.chord_distribution           # blade chord    
    #r                  = rotor.radius_distribution          # radial location   
    #num_sec            = len(r) 
    #num_azi            = len(aeroacoustic_data.disc_effective_angle_of_attack[0,0,:])    
    #U_inf              = np.atleast_2d(np.linalg.norm(velocity_vector,axis=1)).T
    #M                  = U_inf/c_0                                             
    #B                  = rotor.number_of_blades             # number of rotor blades
    #Omega              = aeroacoustic_data.omega            # angular velocity   
    #beta_sq            = 1 - M**2                                  
    #delta_r            = np.zeros_like(r)
    #del_r              = r[1:] - r[:-1]
    #delta_r[0]         = 2*del_r[0]
    #delta_r[-1]        = 2*del_r[-1]
    #delta_r[1:-1]      = (del_r[:-1]+ del_r[1:])/2 
     
    ## Update dimensions for computation
    #r         = np.tile(r[None,None,:,None,None],(num_cpt,num_rot,1,num_azi,num_cf))
    #c         = np.tile(blade_chords[None,None,:,None,None],(num_cpt,num_rot,1,num_azi,num_cf))
    #delta_r   = np.tile(delta_r[None,None,:,None,None],(num_cpt,num_rot,1,num_azi,num_cf))
    #M         = np.tile(M[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,1))  
    #c_0       = np.tile(c_0[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,2))
    #beta_sq   = np.tile(beta_sq[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,2))
    #Omega     = np.tile(Omega[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,2))
    #U_inf     = np.tile(U_inf[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,2))
    #rho       = np.tile(rho[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,2))
    #kine_visc = np.tile(kine_visc[:,None,None,None,None,:],(1,num_rot,num_sec,num_azi,num_cf,2))

    #X   = np.repeat(bspv.blade_section_coordinate_sys[:,i,:,:,:,:,0,:],2,axis = 5)
    #Y   = np.repeat(bspv.blade_section_coordinate_sys[:,i,:,:,:,:,1,:],2,axis = 5)
    #Z   = np.repeat(bspv.blade_section_coordinate_sys[:,i,:,:,:,:,2,:],2,axis = 5)

    ## ------------------------------------------------------------
    ## ****** BLADE MOTION CALCULATIONS ******
    ## the rotational Mach number of the blade section
    #omega   = np.tile((2*np.pi*frequency)[None,None,None,None,:,None],(num_cpt,num_rot,num_sec,num_azi,1,2))
    #r       = np.repeat(r[:,:,:,:,:,np.newaxis],2,axis = 5)
    #c       = np.repeat(c[:,:,:,:,:,np.newaxis],2,axis = 5)/2
    #delta_r = np.repeat(delta_r[:,:,:,:,:,np.newaxis],2,axis = 5)
    #M       = np.repeat(M,2,axis = 5)
    #R_s     = np.repeat(np.linalg.norm(bspv.blade_section_coordinate_sys[:,i,:,:,:,:,:,:],axis = 5),2,axis = 5)
    #mu      = (omega/(1 +(Omega*r/c_0)*(X/R_s)))*M/(U_inf*beta_sq)

    ## ------------------------------------------------------------
    ## ****** LOADING TERM CALCULATIONS ******
    ## equation 7
    #epsilon       = X**2 + (beta_sq)*(Y**2 + Z**2)
    #gamma         = np.sqrt(((mu/epsilon)**2)*(X**2 + beta_sq*(Z**2)))
    #ss_1, cc_1    = fresnel(2*((((omega/(1 +  (Omega*r/c_0)*(X/R_s))) /(0.8*U_inf)) /c) + (mu/c)*M + (gamma/c)))
    #ss_2, cc_2    = fresnel(2*((mu/c)*X/epsilon + (gamma/c)) )
    #triangle      = (omega/(U_inf*c)) - (mu/c)*X/epsilon + (mu/c)*M
    #norm_L_sq     = (1/triangle)*abs(np.exp(1j*2*triangle)*((1 - (1 + 1j)*(cc_1 - 1j*ss_1)) \
                    #+ ((np.exp(-1j*2*triangle))*(np.sqrt((((omega/(1 +  (Omega*r/c_0)*(X/R_s))) /(0.8*U_inf)) + mu*M + gamma)/(mu*X/epsilon +gamma))) \
                       #*(1 + 1j)*(cc_2 - 1j*ss_2)) ))

    ## ------------------------------------------------------------
    ## ****** EMPIRICAL WALL PRESSURE SPECTRUM ******
    
    #Theta      = BL_Data.Theta[:,i,:,:,:,:,:]
    #tau_w      = BL_Data.tau_w[:,i,:,:,:,:,:]
    #dp_dx      = BL_Data.dp_dx[:,i,:,:,:,:,:] 
    #delta      = BL_Data.delta[:,i,:,:,:,:,:]
    #delta_star = BL_Data.delta_star[:,i,:,:,:,:,:]
    #Ue         = BL_Data.Ue[:,i,:,:,:,:,:]
    
    #ones                     = np.ones_like(Theta)
    #beta_c                   = (Theta/tau_w)*dp_dx 
    #d                        = 4.76*((1.4/(delta/delta_star))**0.75)*(0.375*(3.7 + 1.5*beta_c) - 1)
    #a                        = (2.82*((delta/delta_star)**2)*(np.power((6.13*((delta/delta_star)**(-0.75)) + d),(3.7 + 1.5*beta_c))))*\
                               #(4.2*((0.8*((beta_c + 0.5)**3/4))/(delta/delta_star)) + 1)
    #d_star                   = d
    #d_star[beta_c<0.5]       = np.maximum(ones,1.5*d)[beta_c<0.5]
    #Phi_pp_expression        =  (np.maximum(a, (0.25*beta_c - 0.52)*a)*((omega*delta_star/Ue)**2))/(((4.76*((omega*delta_star/Ue)**0.75) \
                                #+ d_star)**(3.7 + 1.5*beta_c))+ (np.power((8.8*(((delta/Ue)/(kine_visc/(((tau_w/rho)**0.5)**2)))**(-0.57))\
                                #*(omega*delta_star/Ue)),(np.minimum(3*ones,(0.139 + 3.1043*beta_c)) + 7)) ))
    #Phi_pp                   = ((tau_w**2)*delta_star*Phi_pp_expression)/Ue
    #Phi_pp[np.isinf(Phi_pp)] = 0.
    #Phi_pp[np.isnan(Phi_pp)] = 0.

    ## Power Spectral Density from each blade
    #mult       = ((omega/c_0)**2)*(c**2)*delta_r*(1/(32*np.pi**2))*(B/(2*np.pi))
    #int_x      = np.linspace(0,2*np.pi,num_azi)    
    #S_pp_azi   = mult*((Z/(X**2 + (1-M**2)*(Y**2 + Z**2)))**2)*norm_L_sq*\
                                              #(1.6*(0.8*U_inf)/omega)*Phi_pp  
    #S_pp_azi[np.isinf(S_pp_azi)] = 0   
    #S_pp       = np.trapz(S_pp_azi,x = int_x,axis = 3)  
    
    ## Sound Pressure Level
    #SPL                          = 10*np.log10((2*np.pi*abs(S_pp))/((p_ref)**2)) 
    #SPL_azi                      = 10*np.log10((2*np.pi*S_pp_azi)/((p_ref)**2))
    #SPL_surf                     = SPL_arithmetic(SPL, sum_axis = 4 )     
    #SPL_rotor                    = SPL_arithmetic(SPL_surf, sum_axis = 2 )   
    #SPL_rotor_dBA                = A_weighting(SPL_rotor,frequency)
    #SPL_surf_azi                 = SPL_arithmetic(SPL_azi, sum_axis = 5 ) 
    #SPL_rotor_azi                = SPL_arithmetic(SPL_surf_azi, sum_axis = 2 ) 
    #SPL_rotor_dBA_azi            = A_weighting(SPL_rotor_azi,frequency)  
    
    ## convert to 1/3 octave spectrum
    #f = np.repeat(np.atleast_2d(frequency),num_cpt,axis = 0)

    #res = Data()
    #res.p_pref_broadband                              = 10**(SPL_rotor /10) 
    #res.p_pref_broadband_dBA                          = 10**(SPL_rotor_dBA /10)   
    #res.SPL_prop_broadband_spectrum                   = SPL_rotor
    #res.SPL_prop_broadband_spectrum_dBA               = A_weighting(SPL_rotor,frequency) 
    #res.SPL_prop_broadband_1_3_spectrum               = SPL_harmonic_to_third_octave(SPL_rotor,f,settings)  
    #res.SPL_prop_broadband_1_3_spectrum_dBA           = SPL_harmonic_to_third_octave(SPL_rotor_dBA,f,settings)   
    #res.azimuthal_broadband_pressure                    = 10**(SPL_rotor_azi /10)   
    #res.azimuthal_broadband_pressure_dBA                = 10**(SPL_rotor_dBA_azi /10)  
    #res.azimuthal_broadband_spectrum_SPL         = SPL_rotor_azi  
    #res.azimuthal_broadband_spectrum_SPL_dBA     = SPL_rotor_dBA_azi  
         
    #return res
 

def compute_rotor_section_boundary_layers(i,airfoil_data,alpha_blade,Re_blade,npanel,airfoil_polar_stations):  

    Re_batch   = np.atleast_2d(Re_blade[i,:,0]).T
    AoA_batch  = np.atleast_2d(alpha_blade[i,:,0]).T       
    AP         = airfoil_analysis(airfoil_data,AoA_batch,Re_batch, npanel, batch_analysis = False, airfoil_stations = airfoil_polar_stations)
    return AP
