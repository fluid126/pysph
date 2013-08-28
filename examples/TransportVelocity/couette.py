"""Couette flow using the transport velocity formulation of Adami et.al."""

# PyZoltan imports
from pyzoltan.core.carray import LongArray

# PySPH imports
from pysph.base.nnps import DomainLimits
from pysph.base.utils import get_particle_array
from pysph.base.kernels import Gaussian, WendlandQuintic, CubicSpline
from pysph.solver.solver import Solver
from pysph.solver.application import Application
from pysph.sph.integrator import TransportVelocityIntegratorStep, Integrator

# the eqations
from pysph.sph.equation import Group
from pysph.sph.wc.transport_velocity import DensitySummation,\
    StateEquation, SolidWallBC, MomentumEquation, ArtificialStress

# numpy
import numpy as np

# domain and reference values
Re = 0.0125
d = 0.5; Ly = 2*d; Lx = 0.4*Ly
rho0 = 1.0; nu = 1.0

# upper wall velocity based on the Reynolds number and channel width
Vmax = nu*Re/(2*d)
c0 = 10*Vmax; p0 = c0*c0*rho0

# Numerical setup
dx = 0.05
ghost_extent = 5 * dx
hdx = 1.2

# adaptive time steps
h0 = hdx * dx
dt_cfl = 0.25 * h0/( c0 + Vmax )
dt_viscous = 0.125 * h0**2/nu
dt_force = 1.0

tf = 2.0
dt = 0.5 * min(dt_cfl, dt_viscous, dt_force)

def create_particles(empty=False, **kwargs):
    if empty:
        fluid = get_particle_array(name='fluid')
        channel = get_particle_array(name='channel')
    else:
        _x = np.arange( dx/2, Lx, dx )

        # create the fluid particles
        _y = np.arange( dx/2, Ly, dx )

        x, y = np.meshgrid(_x, _y); fx = x.ravel(); fy = y.ravel()

        # create the channel particles at the top
        _y = np.arange(Ly+dx/2, Ly+dx/2+ghost_extent, dx)
        x, y = np.meshgrid(_x, _y); tx = x.ravel(); ty = y.ravel()

        # create the channel particles at the bottom
        _y = np.arange(-dx/2, -dx/2-ghost_extent, -dx)
        x, y = np.meshgrid(_x, _y); bx = x.ravel(); by = y.ravel()

        # concatenate the top and bottom arrays
        cx = np.concatenate( (tx, bx) )
        cy = np.concatenate( (ty, by) )

        # create the arrays
        channel = get_particle_array(name='channel', x=cx, y=cy)
        fluid = get_particle_array(name='fluid', x=fx, y=fy)

        print "Couette flow :: Re = %g, nfluid = %d, nchannel=%d, dt = %g"%(
            Re, fluid.get_number_of_particles(),
            channel.get_number_of_particles(), dt)

    # add requisite properties to the arrays:
    # particle volume
    fluid.add_property( {'name': 'V'} )
    channel.add_property( {'name': 'V'} )

    # advection velocities and accelerations
    fluid.add_property( {'name': 'uhat'} )
    fluid.add_property( {'name': 'vhat'} )

    channel.add_property( {'name': 'uhat'} )
    channel.add_property( {'name': 'vhat'} )

    fluid.add_property( {'name': 'auhat'} )
    fluid.add_property( {'name': 'avhat'} )

    fluid.add_property( {'name': 'au'} )
    fluid.add_property( {'name': 'av'} )

    # kernel summation correction for the channel
    channel.add_property( {'name': 'wij'} )

    # imopsed velocity on the channel
    channel.add_property( {'name': 'u0'} )
    channel.add_property( {'name': 'v0'} )

    # magnitude of velocity
    fluid.add_property({'name':'vmag'})

    # setup the particle properties
    if not empty:
        volume = dx * dx

        # mass is set to get the reference density of rho0
        fluid.m[:] = volume * rho0
        channel.m[:] = volume * rho0

        # volume is set as dx^2
        fluid.V[:] = 1./volume
        channel.V[:] = 1./volume

        # smoothing lengths
        fluid.h[:] = hdx * dx
        channel.h[:] = hdx * dx

        # channel velocity on upper portion
        indices = np.where(channel.y > d)[0]
        channel.u0[indices] = Vmax

    # load balancing props
    fluid.set_lb_props( fluid.properties.keys() )
    channel.set_lb_props( solid.properties.keys() )

    # return the particle list
    return [fluid, channel]

# domain for periodicity
domain = DomainLimits(xmin=0, xmax=Lx, periodic_in_x=True)

# Create the application.
app = Application(domain=domain)

# Create the kernel
kernel = Gaussian(dim=2)

print domain, kernel

integrator = Integrator(fluid=TransportVelocityIntegratorStep(),
                        channel=TransportVelocityIntegratorStep())

# Create a solver.
solver = Solver(kernel=kernel, dim=2, integrator=integrator)

# Setup default parameters.
solver.set_time_step(dt)
solver.set_final_time(tf)

equations = [

    # Summation density for the fluid phase
    Group(
        equations=[
            DensitySummation(dest='fluid', sources=['fluid','channel']),
            ]),

    # boundary conditions for the channel wall
    Group(
        equations=[
            SolidWallBC(dest='channel', sources=['fluid',], b=1.0, rho0=rho0, p0=p0),
            ]),

    # acceleration equation
    Group(
        equations=[
            StateEquation(dest='fluid', sources=None, b=1.0, rho0=rho0, p0=p0),

            MomentumEquation(dest='fluid', sources=['fluid', 'channel'], nu=nu),

            ArtificialStress(dest='fluid', sources=['fluid',])

            ]),
    ]

# Setup the application and solver.  This also generates the particles.
app.setup(solver=solver, equations=equations,
          particle_factory=create_particles)

app.run()
