from setuptools import find_packages, setup

setup(name='franca_link',
      version='0.0.1',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      py_modules=['franca_link'],
      install_requires = [
          'flask',
          'lhs_connections'
          #'naviance_calculator_web'
      ]
      )
