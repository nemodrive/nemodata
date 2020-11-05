# NemoData
Tools that facilitate the manipulation of Nemodrive session recordings

## Installation

Clone locally and build using pip:

```
git clone https://github.com/nemodrive/nemodata.git
cd nemodata
pip install .
```

Make sure use your anaconda env (if you so desire) during installation

## Examples

### Playback

To use the player in your own scripts:

```python
from nemodata import Player

with Player("/home/dataset/session_1/") as p:
    for packet in p.stream_generator(loop=False):

        print(packet) # TODO your code here

```

To visualise a recording in human-readable format run the following command:
```
nemoplayer
```

Which will open the graphical user interface

#### Notice:

Due to current GUI limitations you have to pause the video to enable seek functionality.
