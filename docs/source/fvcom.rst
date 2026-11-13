FVCOM output
====================

FVCOM writes its output on an unstructured mesh of triangles, with sigma layers in the vertical.
CDO cannot read FVCOM files directly, so nctoolkit has a dedicated function for opening them: ``open_fvcom``.

Opening FVCOM output
-----------------------

By default all the variables on the nodes of the mesh (and on the sigma layers, or with no vertical axis) are opened.
A warning lists the variables that were left out, as they cannot share a grid with these.
You can instead say which variables you want:

.. code:: ipython3

    import nctoolkit as nc
    ds = nc.open_fvcom("fvcom_0001.nc")
    ds = nc.open_fvcom("fvcom_0001.nc", variables=["temp", "salinity"])

You can give a list of files or a wildcard, e.g. ``nc.open_fvcom("output/*.nc", "temp")``. Each FVCOM file becomes one file in the dataset.

The variables you supply must all be on the nodes of the mesh (e.g. ``temp``, ``salinity``, ``zeta``) or all be on the elements (e.g. ``u``, ``v``, ``ua``).
To work with both, open them separately. Element variables such as ``u`` and ``v`` are never opened by default, so supply them, e.g. ``variables=["u", "v"]``.

``open_fvcom`` puts the data on a grid that CDO understands:

* each node, or element, is a grid cell with its true area. The cells of the nodes are FVCOM's own control volumes (whose areas FVCOM stores as ``art1``), and the cells of the elements are their triangles.
* the sigma layers become vertical levels, numbered from 1 at the surface.
* the thickness of each layer, ``(siglev[k] - siglev[k + 1]) * (h + zeta)``, is added as a variable called ``layer_thickness``. This changes with the free surface at each time step.

The dataset has two attributes that record this:

.. code:: ipython3

    ds.fvcom            # True
    ds.fvcom_thickness  # "layer_thickness"


Vertical methods
-------------------

The vertical methods use the layer thickness automatically, so you do not need to supply ``thickness`` or ``fixed``:

.. code:: ipython3

    ds.vertical_mean()                       # thickness-weighted depth average
    ds.vertical_integration()                # depth integral
    ds.vertical_mean(depth_range=[0, 20])    # the top 20 m
    ds.vertical_interp([5, 10, 50])          # values at fixed depths below the surface
    ds.top()                                 # the surface layer
    ds.bottom()                              # the bottom layer

When interpolating to fixed depths, depths above the centre of the top layer take the top layer's value,
depths between the centre of the bottom layer and the seabed take the bottom layer's value,
and depths below the seabed are missing.

The thickness must still be in the dataset. If you select variables, keep it:

.. code:: ipython3

    ds.subset(variables=["temp", "layer_thickness"])

Note that arithmetic with a constant, e.g. ``ds.add(1)``, also changes the layer thickness.


Spatial averages and regridding
----------------------------------

Because every cell has its true area, spatial statistics are area weighted:

.. code:: ipython3

    ds.spatial_mean()
    ds.crop(lon=[-6, -4], lat=[50, 51])
    ds.cell_area()

Regridding works out weights on the mesh itself. The ``bil`` method (the default) interpolates linearly within the mesh's triangles.
``nn`` takes the nearest node, or the element a point is in. Places outside the mesh are missing, as are places next to missing values.

.. code:: ipython3

    ds.to_latlon(lon=[-10, -2], lat=[48, 57], res=0.05)
    ds.regrid(grid_ds)
    ds.to_transect(start=[-6, 50], end=[-4, 51])
    ds.match_points(df)

``con``, ``con2``, ``laf`` and ``dis`` are also available.
Once regridded, the data is no longer on the FVCOM mesh, so ``ds.fvcom`` is False, but the vertical methods still use the layer thickness.


What does not work with FVCOM data
--------------------------------------

The following methods need a regular grid, or otherwise make no sense on the mesh.
They raise an error saying they do not work with FVCOM data. Regrid the data first, e.g. using ``to_latlon``, if you need them.

* ``zonal_mean``, ``zonal_sum``, ``zonal_min``, ``zonal_max``, ``zonal_range``
* ``meridonial_mean``, ``meridonial_min``, ``meridonial_max``, ``meridonial_range``
* ``box_mean``, ``box_sum``, ``box_min``, ``box_max``, ``box_range``
* ``resample_grid``, ``distribute``
* ``invert("latitudes")``
* ``strip_variables``, which would remove the mesh's coordinates
* ``set_gridtype``, ``fix_amm7_grid``, ``fix_nemo_ersem_grid``
* ``generate_level_bounds``, and ``vertical_mean``/``vertical_integration``/``vertical_interp`` with ``fixed=True``
* ``crop`` with ``nco=True``

All other methods work as they do for any other data.
