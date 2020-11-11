from setuptools import setup

setup(
    name='nemodata',
    version='0.1',
    description='Tools that facilitate the manipulation of Nemodrive session recordings',
    url='https://github.com/nemodrive/nemodata',
    packages=['nemodata'],
    install_requires=[
        'numpy',
        'scipy',
        'opencv-python',
        'PyQt5',
        'pyqtgraph',
    ],
    # scripts=['scripts/nemoplayer'],
    entry_points={
          'console_scripts': ['nemoplayer=nemodata.gui_player:main']
    },
    include_package_data=True,
    classifiers=[
        # TODO
    ],
)
