from setuptools import find_packages, setup

setup(name='franca_link',
      version='0.0.1',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      py_modules=['franca_link'],
      install_requires = [
          'flask',
          'logging_franca_link @ git+https://github.com/francaellerman/logging_franca_link',
          'lhs_connections @ git+https://github.com/francaellerman/lhs_connections'
          #'naviance_calculator_web'
      ]
      )
