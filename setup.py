from setuptools import find_packages, setup

setup(name='franca_link',
      version='0.0.1',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      #py_modules=['franca_link'],
      install_requires = [
          'flask==2.2.1',
          'pdfminer==20191125',
          'pdfminer.six==20220524',
          'PyPDF2==2.6.0',
          'tabula-py==2.4.0',
          'pandas==1.4.2',
          'icalendar==4.1.0',
          'pyyaml==5.4.1',
          'python-magic==0.4.27',
          'pyffx==0.3.0',
          'naviance_admissions_calculator_web @ git+https://github.com/francaellerman/naviance_admissions_calculator_web'
      ]
      )
