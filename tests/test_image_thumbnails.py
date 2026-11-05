from __future__ import annotations

import os
import shutil
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from PIL import Image

from tests._plugin_import import load as load_plugin
from tests._temp_dir import make_temp_dir

thumbnails = load_plugin("comfyui.image_thumbnails")


class ImageThumbnailTest(unittest.TestCase):
    def setUp(self):
        self.input_dir = make_temp_dir(prefix="h3lvm_thumb_input_")
        self.cache_dir = make_temp_dir(prefix="h3lvm_thumb_cache_")
        self.roots = {"input": self.input_dir}

    def tearDown(self):
        shutil.rmtree(self.input_dir, ignore_errors=True)
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def write_image(self, name="source.png", size=(1024, 512), color=(255, 0, 0)):
        path = os.path.join(self.input_dir, name)
        Image.new("RGB", size, color).save(path)
        return path

    def entry(self, name="source.png"):
        return {"filename": name, "subfolder": "", "type": "input"}

    def make(self, name="source.png"):
        return thumbnails.thumbnail_path(self.entry(name), self.roots, self.cache_dir)

    def test_thumbnail_is_bounded_and_metadata_keeps_source_size(self):
        source = self.write_image()
        target = self.make()
        with Image.open(target) as image:
            self.assertEqual(image.size, (512, 256))
            self.assertEqual(image.format, "JPEG")
        self.assertEqual(thumbnails.image_metadata(self.entry(), self.roots),
                         {"width": 1024, "height": 512})
        self.assertTrue(os.path.commonpath([self.cache_dir, target]) == self.cache_dir)
        self.assertTrue(os.path.isfile(source))

    def test_cached_and_concurrent_reads_decode_once(self):
        self.write_image()
        real_open = thumbnails.Image.open
        with mock.patch.object(thumbnails.Image, "open", wraps=real_open) as opened:
            with ThreadPoolExecutor(max_workers=4) as pool:
                paths = list(pool.map(lambda _index: self.make(), range(4)))
            self.assertEqual(self.make(), paths[0])
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(opened.call_count, 1)

    def test_replacing_the_same_name_invalidates_the_cache(self):
        self.write_image(size=(100, 100))
        first = self.make()
        self.write_image(size=(200, 100), color=(0, 0, 255))
        second = self.make()
        self.assertNotEqual(first, second)
        self.assertEqual(thumbnails.image_metadata(self.entry(), self.roots)["width"], 200)
        with Image.open(second) as image:
            self.assertEqual(image.size, (200, 100))

    def test_exif_orientation_is_applied_to_pixels_and_metadata(self):
        path = os.path.join(self.input_dir, "rotated.jpg")
        image = Image.new("RGB", (640, 320), (10, 20, 30))
        exif = Image.Exif()
        exif[274] = 6
        image.save(path, exif=exif)
        self.assertEqual(thumbnails.image_metadata(self.entry("rotated.jpg"), self.roots),
                         {"width": 320, "height": 640})
        with Image.open(self.make("rotated.jpg")) as thumb:
            self.assertEqual(thumb.size, (256, 512))

    def test_unsafe_paths_and_non_images_are_refused(self):
        for name in ("../outside.png", "/absolute.png"):
            with self.assertRaises(ValueError):
                self.make(name)
        with open(os.path.join(self.input_dir, "voice.mp3"), "wb") as stream:
            stream.write(b"not an image")
        with self.assertRaises(ValueError):
            self.make("voice.mp3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
