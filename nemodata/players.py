from typing import Iterator, Optional, Tuple, Union
from copy import deepcopy
import os

import numpy as np
import pickle

import cv2

import logging

import datetime

from .compression import JITDecompressor


class VideoReadBuffer:
    """Wrapper for the chosen video player backend, which also keeps track of the read frame indices."""

    def __init__(self, path: str):
        """
        Instantiates the buffer with the parameters of the video that will be played.

        Args:
            path (str): Path to the video file
        """

        self.path = path

        self._video_capture = cv2.VideoCapture(self.path)

        self.resolution = (
            self._video_capture.get(cv2.CAP_PROP_FRAME_WIDTH),
            self._video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        )

        self._crt_frame = 0

    def set_frame(self, frame_number: int):
        """
        Go to a specific frame in the video.

        Args:
            frame_number (int): Zero indexed frame number
        """

        self._video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        self._crt_frame = frame_number

    def read_frame(self) -> np.ndarray:
        """
        Get the next frame in the video.
        The frame will be returned and the buffer will advance by one frame.

        Returns:
            np.ndarray: Frame as OpenCV format image
        """

        res, frame = self._video_capture.read()
        self._crt_frame += 1
        return frame

    def get_crt_frame_number(self) -> int:
        """
        Get index of the current frame.
        This is the index of the frame that will be returned when read_frame() is called

        Returns:
            int: Zero indexed frame number
        """
        return self._crt_frame

    def close(self):
        """Closes the video file and cleans all used resources."""
        self._video_capture.release()


class Player:
    """Plays back a dataset recorded using a Recorder object"""

    def __init__(self,
                 in_path: Optional[str] = "./test_recording/",
                 compute_indices: Optional[bool] = True,
                 enabled_positions: Optional[Tuple[str]] = ("center", "left", "right")
                 ):
        """
        Instantiates the Player with the details of the dataset that will be played back.
        To be ready for playback start() needs to be called.
        This is done automatically if the Player is called within a Python "with" statement.

        Args:
            in_path (Optional[str]): Directory where the dataset is found on disk
            compute_indices (Optional[bool]): If true seeking options for the dataset will be enabled
            enabled_positions (Optional[Tuple[str]]): Names of the cameras to be used (e.g. ("center", "left"))
        """

        self.in_path = in_path
        self.enabled_positions = enabled_positions
        self.open_videos = {}
        self.metadata_file = None
        self.uses_indices = compute_indices
        self._crt_frame_index = 0
        self.indices = []
        self.start_datetime = None
        self.end_datetime = None

    def start(self):
        """
        Opens the video files and makes sure the Player is ready to stream data.
        Is called automatically by __enter__() if the Player is called within a Python "with" statement.
        """

        self.metadata_file = open(os.path.join(self.in_path, "metadata.pkl"), "rb")

        video_paths = pickle.load(self.metadata_file)

        for pos in self.enabled_positions:
            self.open_videos[pos] = VideoReadBuffer(os.path.join(self.in_path, video_paths[pos]))

        if self.uses_indices:
            logging.info("Player now computing indices...")

            while True:
                self.indices.append(self.metadata_file.tell())
                try:
                    crt_frame = pickle.load(self.metadata_file)
                except (EOFError, pickle.UnpicklingError):
                    self.indices.pop()
                    break

            self.metadata_file.seek(self.indices[-1], 0)
            last_frame = pickle.load(self.metadata_file)
            self.end_datetime = last_frame["datetime"]

            self.metadata_file.seek(self.indices[0], 0)
            first_frame = pickle.load(self.metadata_file)
            self.start_datetime = first_frame["datetime"]

            self.metadata_file.seek(self.indices[0], 0)

            logging.info(f"Indices built for {len(self.indices)} frames!")

    def close(self):
        """Closes video and metadata files and cleans all used resources."""
        self.metadata_file.close()

        for video_reader in self.open_videos.values():
            video_reader.close()

    def __enter__(self):
        """This allows the Player to be (optionally) used in Python 'with' statements"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """This allows the Player to be (optionally) used in Python 'with' statements"""
        self.close()

    def __len__(self):
        if self.uses_indices:
            return len(self.indices)
        else:
            raise Exception("Cannot use len() on player that has no frame indices")

    @property
    def crt_frame_index(self):
        return self._crt_frame_index

    @crt_frame_index.setter
    def crt_frame_index(self, value):

        if self.uses_indices:

            if not 0 <= value < len(self.indices):
                raise Exception(f"Out of range seek to frame index {value} in a {len(self.indices)} frame video")

            self._crt_frame_index = value

            self.metadata_file.seek(self.indices[value], 0)

            # TODO these will cause a little lag on video restart as they are set automatically to the correct values
            # TODO could maybe explore a few frames in this region and set the correct frame indices from here
            # for pos in self.enabled_positions:
            #     self.open_videos[pos].set_frame(value)

        else:
            raise Exception("Cannot use len() on player that has no frame indices")

    def get_next_packet(self) -> Optional[Union[dict, None]]:
        """
        Return the next packet in the recording.
        Recording will advance to the next packet after get_next_packet() is called.


        Returns:
            Optional[Union[dict, None]]: Read data packet. If recording has finished returns None.
        """

        try:
            packet_small = pickle.load(self.metadata_file)
            self._crt_frame_index += 1
        except (EOFError, pickle.UnpicklingError):
            return None

        if "images" in packet_small:
            # a packet with images, get them from the videos

            packet_big = deepcopy(packet_small)

            for pos, img_num in packet_small["images"].items():

                if img_num is None:
                    packet_big["images"][pos] = None
                else:
                    if not img_num == self.open_videos[pos].get_crt_frame_number():
                        logging.debug("Frame index differs from video index! Attempting automatic resync!")
                        self.open_videos[pos].set_frame(img_num)

                    img = self.open_videos[pos].read_frame()
                    packet_big["images"][pos] = img

            return packet_big
        else:
            return packet_small

    def rewind(self):
        """Rewinds the dataset, the next packet returned by the stream will be the first packet in the dataset"""

        self._crt_frame_index = 0

        self.metadata_file.seek(0, 0)

        video_paths = pickle.load(self.metadata_file)

        for pos in self.enabled_positions:
            self.open_videos[pos].set_frame(0)

    def stream_generator(self, loop: Optional[bool] = False) -> Iterator[dict]:
        """
        Wraps get_next_packet() in the form of a generator for convenience.

        Args:
            loop (Optional[bool]): If true will perform rewind() automatically when the dataset reaches its end.

        Returns:
            Iterator[dict]: Generator providing played back packets

        """

        while True:
            while packet := self.get_next_packet():
                yield packet

            if loop:
                self.rewind()
                continue
            else:
                break


class VariableSampleRatePlayer(Player):

    def __init__(self,
                 in_path: Optional[str] = "./test_recording/",
                 min_packet_delay_ms: Optional[int] = 300,
                 compute_indices: Optional[bool] = True,
                 enabled_positions: Optional[Tuple[str]] = ("center", "left", "right")
                 ):
        """
        Instantiates the Player with the details of the dataset that will be played back.
        To be ready for playback start() needs to be called.
        This is done automatically if the Player is called within a Python "with" statement.

        VariableSampleRatePlayer allows you to specify a minimum delay time between packets.
        Data is merged between packets that come before the delay period ends, and then output as a single packet.
        This can be used to simulate a lower framerate recording.

        Args:
            in_path (Optional[str]): Directory where the dataset is found on disk
            min_packet_delay_ms (Optional[int]): skips packets until their time difference is bigger than this value
            compute_indices (Optional[bool]): If true seeking options for the dataset will be enabled
            enabled_positions (Optional[Tuple[str]]): Names of the cameras to be used (e.g. ("center", "left"))
        """

        super(VariableSampleRatePlayer, self).__init__(in_path, compute_indices, enabled_positions)

        self.min_packet_delay_ms = min_packet_delay_ms
        self._decompressor = JITDecompressor()

    @property
    def crt_frame_index(self):
        return Player.crt_frame_index.fget(self)

    @crt_frame_index.setter
    def crt_frame_index(self, value):
        Player.crt_frame_index.fset(self, value)
        self._decompressor.rewind()

    def get_next_packet(self) -> Optional[Union[dict, None]]:
        """
        Return the next packet in the recording.
        Recording will advance to the next packet after get_next_packet() is called.


        Returns:
            Optional[Union[dict, None]]: Read data packet. If recording has finished returns None.
        """

        initial_packet = super(VariableSampleRatePlayer, self).get_next_packet()

        if initial_packet is None:
            self._decompressor.rewind()
            return None
        else:

            next_packet = super(VariableSampleRatePlayer, self).get_next_packet()

            if next_packet is None:
                self._decompressor.rewind()
                return initial_packet

            self._decompressor.decompress_next_packet(initial_packet)

            d_next_packet = self._decompressor.decompress_next_packet(next_packet)

            time_diff = d_next_packet["datetime"] - initial_packet["datetime"]

            while time_diff.total_seconds() * 1000 < self.min_packet_delay_ms:

                next_packet = super(VariableSampleRatePlayer, self).get_next_packet()
                d_next_packet = self._decompressor.decompress_next_packet(next_packet)

                time_diff = d_next_packet["datetime"] - initial_packet["datetime"]

            self._decompressor.rewind()
            return d_next_packet

    def rewind(self):
        """Rewinds the dataset, the next packet returned by the stream will be the first packet in the dataset"""
        super(VariableSampleRatePlayer, self).rewind()
        self._decompressor.rewind()
