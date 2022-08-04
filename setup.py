from setuptools import find_packages, setup

setup(name='franca_link',
      version='0.0.1',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      #py_modules=['franca_link'],
      install_requires = [
          'flask',
          'pdfminer',
          'pdfminer.six',
          'PyPDF2',
          'tabula-py',
          'pandas',
          'icalendar',
          'pyyaml',
          'naviance_admissions_calculator_web @ git+https://github.com/francaellerman/naviance_admissions_calculator_web'
      ]
      )
