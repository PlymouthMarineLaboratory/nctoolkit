.. currentmodule:: nctoolkit


####################
API Reference
####################

Session options
------------------

.. autosummary::
   :toctree: generated/

   options


Opening/copying data
------------------

.. autosummary::
   :toctree: generated/

   open_data
   open_url
   open_thredds
   open_geotiff
   open_fvcom
   from_xarray 
   DataSet.copy

Merging or analyzing multiple datasets
------------------

.. autosummary::
   :toctree: generated/

    merge
    cor_time
    cor_space
    

Adding and removing files to a dataset
------------------

.. autosummary::
   :toctree: generated/

    DataSet.append
    DataSet.remove

Accessing attributes
------------------

.. autosummary::
   :toctree: generated/

   DataSet.variables
   DataSet.contents
   DataSet.times
   DataSet.years
   DataSet.months
   DataSet.levels
   DataSet.size
   DataSet.current
   DataSet.history
   DataSet.start
   DataSet.calendar
   DataSet.ncformat

Plotting
------------------

.. autosummary::
   :toctree: generated/

   DataSet.plot
   DataSet.pub_plot


Variable modification 
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.assign
   DataSet.rename
   DataSet.as_missing
   DataSet.missing_as
   DataSet.set_fill
   DataSet.sum_all

netCDF file attribute modification 
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.set_longnames
   DataSet.set_units

Vertical/level methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.top
   DataSet.bottom
   DataSet.vertical_interp
   DataSet.vertical_mean
   DataSet.vertical_min
   DataSet.vertical_max
   DataSet.vertical_range
   DataSet.vertical_sum
   DataSet.vertical_integration
   DataSet.vertical_cumsum
   DataSet.invert_levels
   DataSet.bottom_mask



Rolling methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.rolling_mean
   DataSet.rolling_min
   DataSet.rolling_max
   DataSet.rolling_sum
   DataSet.rolling_range
   DataSet.rolling_stdev
   DataSet.rolling_var



Evaluation setting
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.run


Cleaning functions
---------------------

.. autosummary::
   :toctree: generated/

   cleanup()
   deep_clean()

=======

Ensemble creation
---------------------

.. autosummary::
   :toctree: generated/

   create_ensemble

Arithemetic methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.abs
   DataSet.add
   DataSet.assign
   DataSet.exp
   DataSet.log
   DataSet.log10
   DataSet.multiply
   DataSet.power
   DataSet.sqrt
   DataSet.square
   DataSet.subtract
   DataSet.divide


Ensemble statistics
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.ensemble_mean
   DataSet.ensemble_min
   DataSet.ensemble_max
   DataSet.ensemble_percentile
   DataSet.ensemble_range
   DataSet.ensemble_stdev
   DataSet.ensemble_sum
   DataSet.ensemble_var


Subsetting operations
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.subset
   DataSet.crop
   DataSet.drop

Time-based methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.set_date
   DataSet.set_day
   DataSet.shift

Interpolation, matching and resampling methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.regrid
   DataSet.to_latlon
   DataSet.match_points
   DataSet.resample_grid
   DataSet.time_interp
   DataSet.timestep_interp
   DataSet.fill_na
   DataSet.box_mean
   DataSet.box_max
   DataSet.box_min
   DataSet.box_sum
   DataSet.box_range


Masking methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.mask_box


Anomaly methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.annual_anomaly
   DataSet.monthly_anomaly




Statistical methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.tmean
   DataSet.tmin
   DataSet.tmedian
   DataSet.tpercentile
   DataSet.tmax
   DataSet.tsum
   DataSet.trange
   DataSet.tstdev
   DataSet.tcumsum
   DataSet.tvar

   DataSet.cor_space
   DataSet.cor_time

   DataSet.spatial_mean
   DataSet.spatial_min
   DataSet.spatial_max
   DataSet.spatial_percentile
   DataSet.spatial_range
   DataSet.spatial_sum
   DataSet.spatial_stdev
   DataSet.spatial_var

   DataSet.centre

   DataSet.zonal_mean
   DataSet.zonal_min
   DataSet.zonal_max
   DataSet.zonal_range
   DataSet.zonal_sum

   DataSet.meridonial_mean
   DataSet.meridonial_min
   DataSet.meridonial_max
   DataSet.meridonial_range




Merging methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.merge


Splitting methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.split


Output and formatting methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.to_nc
   DataSet.to_xarray
   DataSet.to_dataframe
   DataSet.zip
   DataSet.format

Miscellaneous methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.na_count
   DataSet.na_frac
   DataSet.distribute
   DataSet.collect
   DataSet.cell_area
   DataSet.first_above
   DataSet.first_below
   DataSet.last_above
   DataSet.last_below
   DataSet.cdo_command
   DataSet.nco_command
   DataSet.compare
   DataSet.gt
   DataSet.lt
   DataSet.reduce_dims
   DataSet.reduce_grid
   DataSet.set_precision
   DataSet.check
   DataSet.is_corrupt
   DataSet.fix_nemo_ersem_grid
   DataSet.set_gridtype
   DataSet.surface_mask
   DataSet.strip_variables
   DataSet.no_leaps
   DataSet.as_double
   DataSet.as_type
   DataSet.reset



Ecological methods
---------------------

.. autosummary::
   :toctree: generated/

   DataSet.phenology








