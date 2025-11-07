from setuptools import setup, find_packages

setup(
    name='pointer_telemetry',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        "Flask>=3.0,<4",
        "Flask-SQLAlchemy>=3.1,<4",
        "SQLAlchemy>=2.0,<3"
    ]
)
