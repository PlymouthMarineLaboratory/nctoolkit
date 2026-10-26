
####################
Data supported
####################

nctoolkit will support analysis of most netCDF data. However, there are some limitations and requirements.
Most operations in nctoolkit rely on Climate Data Operators (CDO) to perform the heavy lifting.
CDO requires that files have at most 4 dimensions, which should be longitude and latitude, and time and depth/height. 
It provides support for structured grids such as regular lon/lat or curvilinear grids, and unstructured grids.

Horizontal grids
------------------

nctoolkit will work with more or less any structured horizontal grid, so long as it follows the GDT, COARDS or CF conventions. 


It provides limited supported for unstructured horizontal grids. These grids are often idiosyncratic and require special treatment and therefore only limited functionality is available in CDO.
However, interpolation via the nearest neighbour method is supported. In some cases, the metadata of the netCDF file may need to be changed to allow CDO to work with the data. 
So, if you are working with unstructured data and running into problems, reach out to us at the `nctoolkit Discussions page <https://github.com/PlymouthMarineLaboratory/nctoolkit/discussions>`__).

In some cases methods may not be able to provide a fully accurate answer due to deficiencies in the underlying file metadata. 
For example, the `spatial_mean` method needs to be able to calculate the area of each grid cell, but sometimes data providers fail to include this information in their files. 
In such cases, warning messages will be printed to the screen, but you can reach out to us if you want a fix for data problems.

Vertical grids
------------------

nctoolkit provides support for vertical grids that have either consistent or varying horizontal levels. So, in almost all cases it will work with your data.
Occasionally, you may run into problems due to deficiencies in the raw netCDF files. 
For example, for vertical averaging to be totally accurate, the thickness of each vertical level is required.
However, sometimes files do not contain this information, and there is no way to infer it. 
At present, nctoolkit is focused on analyzing data, not correcting, and therefore is not designed to fix issues in the raw files. 
However, if you run into any contact us `here <https://github.com/PlymouthMarineLaboratory/nctoolkit/discussions>`__) and we can help you.

The time axis
------------------

So long as your time axis is CF-compliant, nctoolkit should have no problem handling it. However, CDO requires only one time axis. 
If you have multiple time axes, it will pick one. This is almost never an issue, unless you have very idiosyncratic time axes.

Data types
------------------

nctoolkit supports all data types that CDO supports. This includes 32-bit and 64-bit floating point numbers, and 8-bit, 16-bit and 32-bit integers.
By default CDO, and therefore nctoolkit, will use the data type of the netCDF file for any computations. In general, this is not an issue.
However, some times you need to be careful when you are working with files with integer data formats. These may need to be changed to float using the `set_precision` method.

Similarly, you may run into rare problems due to poorly defined netCDF files that cause computational problems. 
For example, netCDF files can have poorly defined maximum values that result in errors when carrying out simple calculations. 



How to check if your files are CF compliant
---------------------------------------

If you are unsure if your files are CF compliant, you can check them using the `CF checker <http://cfconventions.org/compliance-checker.html>`__.
This is a great tool that will check your files for compliance with the CF conventions. If this throws any errors, then you might have issues analyzing the file with nctoolkit.
An error would imply that it is not possible for CDO to figure out the structure of the file, and therefore it will not be able to perform certain operations on it.
Most of the time you can fix these problems with CDO or NCO, so reach out to us if you need help.

How to deal with data problems
---------------------------------------

nctoolkit is designed primarily as a data analysis package. At present, it provides minimal functionality for fixing problems in the raw data, especially in the metadata.
This is expected to change in future releases. However, until then it is best to reach out to us if you run into problems. These can typically be solved using either NCO or CDO.
