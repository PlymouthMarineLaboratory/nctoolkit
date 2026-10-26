
<!-- README.md is generated from README.Rmd. Please edit that file -->

<p align="center">
  <img src="docs-site/assets/img/nctoolkit_wordmark.svg" alt="NCToolkit" width="320">
</p>

<p align="center"><strong>From raw netCDF to answers, fast &mdash; <a href="https://plymouthmarinelaboratory.github.io/nctoolkit/">see the full docs, quickstart and API reference</a></strong></p>

[![pypi](https://img.shields.io/pypi/v/nctoolkit.svg)](https://pypi.python.org/pypi/nctoolkit/)
[![Conda Latest Release](https://anaconda.org/conda-forge/nctoolkit/badges/version.svg)](https://anaconda.org/conda-forge/nctoolkit/)
[![contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg?style=flat)](https://github.com/PlymouthMarineLaboratory/nctoolkit/issues) 
[![codecov](https://codecov.io/gh/PlymouthMarineLaboratory/nctoolkit/branch/master/graph/badge.svg)](https://codecov.io/gh/PlymouthMarineLaboratory/nctoolkit)
![GitHub Testing](https://github.com/PlymouthMarineLaboratory/nctoolkit/actions/workflows/python-app-linux.yml/badge.svg)
![GitHub Testing macOS](https://github.com/PlymouthMarineLaboratory/nctoolkit/actions/workflows/python-app-macos.yml/badge.svg)
[![DOI](https://joss.theoj.org/papers/10.21105/joss.05494/status.svg)](https://doi.org/10.21105/joss.05494)






# NCToolkit - A Python package for netCDF analysis and post-processing 

NCToolkit is a comprehensive Python (3.8 and above) package for analyzing netCDF data on Linux and macOS.

Core abilities include:
   - Clipping to spatial regions
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
   - Calculating phenological metrics

[![PML logo](docs/source/pml-logo.gif)](https://pml.ac.uk/)


## Installation

The easiest way to install the package is using conda or mamba. This will install NCToolkit and all system dependencies.
```sh
conda install -c conda-forge nctoolkit
mamba install -c conda-forge nctoolkit
```

If you install using conda, please be aware that conda can install a very old version of NCToolkit. Consider setting it to a more recent version.

Install through [PyPI](https://pypi.org/project/nctoolkit/) using pip:
```sh
pip install nctoolkit 
```

Install the development version using using pip:
```sh
pip install git+https://github.com/PlymouthMarineLaboratory/nctoolkit.git
```

This package requires the installation of [Climate Data Operators](https://code.mpimet.mpg.de/projects/cdo/wiki). The conda installation will handle this for you. Otherwise, you will have to install it.  The easiest way is using conda:

```sh
conda install -c conda-forge cdo 
```

A couple of methods give users the option of using [NetCDF Operators](http://nco.sourceforge.net/) instead of CDO as the computational backend. Again, the easiest way to install is using conda:

```sh
conda install -c conda-forge nco 
```

If you want to install CDO from source, bash scripts are available [here](https://github.com/PlymouthMarineLaboratory/nctoolkit/tree/master/cdo_installers).
 
NCToolkit is tested with continuous integration using Circle CI and GitHub Actions (on both Linux and macOS). It will not work on Windows platforms today or in future, because of system dependency limitations. 


## Reference and tutorials

A full API reference, in depth tutorials and a how-to guide are available at [plymouthmarinelaboratory.github.io/nctoolkit](https://plymouthmarinelaboratory.github.io/nctoolkit/).



## Contributing

If you're interested in contributing to NCToolkit, feel free to open an issue or start a [discussion](https://github.com/PlymouthMarineLaboratory/nctoolkit/discussions) on GitHub.

## Got questions about NCToolkit? 

- If you have a question about how to use NCToolkit, please ask on 
    [GitHub Discussions](https://github.com/PlymouthMarineLaboratory/nctoolkit/discussions).
- Report any bugs, suggest new features or view the source code [on
    GitHub](https://github.com/PlymouthMarineLaboratory/nctoolkit).

















