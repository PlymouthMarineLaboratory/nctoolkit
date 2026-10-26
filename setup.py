from setuptools import Command, find_packages, setup
import sys

DESCRIPTION = "A Python package for netCDF analysis and post-processing"
LONG_DESCRIPTION = """

**nctoolkit** is a comprehensive Python (3.10 and above) package for analyzing netCDF data on Linux and macOS.

Core abilities of nctoolkit include:

  - Clipping to spatial region
  - Calculating climatologies
  - Subsetting to specific time periods
  - Calculating spatial statistics
  - Creating new variables using arithmetic operations
  - Calculating anomalies
  - Calculating rolling and cumulative statistics
  - Horizontally and vertically remapping data
  - Calculating time averages
  - Interactive plotting of data
  - Calculating the correlations between variables
  - Calculating vertical statistics for the likes of oceanic data
  - Calculating ensemble statistics

Operation of the package requires the installation of Climate Data Operators (CDO). This is the computational backend for most of the methods used. No knowledge of CDO is required to use nctoolkit. A couple of methods provide users with the option of using netCDF Operators (NCO) as a backend. Guidance for how to install the backends are available `here <https://plymouthmarinelaboratory.github.io/nctoolkit/installing.html>`__.

The package is designed for both intensive bulk processing of NetCDF files and interactive Jupyter notebook analysis. It features an interactive plotting feature which allows users to view the contents of NetCDF files either within Jupyter notebooks or a web browser.

Plotting requires the use of cartopy, which has some additional system dependencies. Follow the instructions `here <https://scitools.org.uk/cartopy/docs/latest/installing.html>`__ to install them.

Documentation and a user guide are available `here <https://plymouthmarinelaboratory.github.io/nctoolkit/>`__.

"""

PROJECT_URLS = {
    "Bug Tracker": "https://github.com/PlymouthMarineLaboratory/nctoolkit/issues",
    "Documentation": "https://plymouthmarinelaboratory.github.io/nctoolkit/",
    "Source Code": "https://github.com/PlymouthMarineLaboratory/nctoolkit",
}

extras_require: dict() = dict()


extras_require["complete"] = ["geoviews", "rioxarray", "cfchecker", "geocube", "geopandas"]

REQUIREMENTS = [i.strip() for i in open("requirements.txt").readlines()]

setup(name='nctoolkit',
      version='1.3.10',
      description=DESCRIPTION,
      long_description=LONG_DESCRIPTION,
      long_description_content_type='text/plain',
      python_requires='>=3.10',
      classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
    ],

      project_urls=PROJECT_URLS,
      url = "https://github.com/PlymouthMarineLaboratory/nctoolkit",
      author='Robert Wilson',
      maintainer='Robert Wilson',
      author_email='rwi@pml.ac.uk',

      packages = ["nctoolkit"],
      install_requires = REQUIREMENTS,
      extras_require = extras_require,
      zip_safe=False)




