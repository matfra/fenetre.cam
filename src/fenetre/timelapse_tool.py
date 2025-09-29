from absl import app, flags

from fenetre import timelapse
from fenetre.logging_utils import setup_logging

FLAGS = flags.FLAGS

flags.DEFINE_string("dir", None, "directory to build a timelapse from")
flags.DEFINE_bool("overwrite", False, "Overwrite existing timelapse")
flags.DEFINE_bool(
    "two_pass", False, "Tell ffmpeg to do 2 pass encoding. Recommended for VP9"
)
flags.mark_flag_as_required("dir")


def main(argv):
    del argv  # Unused.
    setup_logging(FLAGS.log_dir)
    timelapse.create_timelapse(
        FLAGS.dir, FLAGS.overwrite, FLAGS.two_pass, FLAGS.log_dir
    )


def run():
    app.run(main)


if __name__ == "__main__":
    run()
