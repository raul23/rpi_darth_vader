import argparse
import logging.config
import os
import platform
import threading
import time

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame

from logging import NullHandler

from darth_vader_rpi import __name__ as package_name, __version__
from darth_vader_rpi.utils import (get_cfg_filepath, load_json,
                                   msg_with_spaces, override_config_with_args,
                                   run_cmd)


logger = logging.getLogger(__name__)
logger.addHandler(NullHandler())


class SoundWrapper:
    def __init__(self, name, filepath, channel_obj):
        self.name = name
        self.filepath = filepath
        self.channel_obj = channel_obj
        # Load sound file
        self.pygame_sound = pygame.mixer.Sound(self.filepath)

    def play(self, loops=0):
        self.channel_obj.play(self.pygame_sound, loops)

    def stop(self):
        self.channel_obj.stop()


def run_led_sequence(led_channels):
    # TODO: assert led_channels, i.e. keys (top, ...)
    t = threading.currentThread()
    seq_idx = 0
    sequence = [[led_channels['top'], led_channels['bottom']],
                [led_channels['top']],
                [led_channels['bottom']],
                [led_channels['middle'], led_channels['bottom']],
                [led_channels['middle']],
                [led_channels['top'], led_channels['middle']],
                [led_channels['top'], led_channels['middle'], led_channels['bottom']]]
    while getattr(t, "do_run", True):
        leds_step = sequence[seq_idx % len(sequence)]
        seq_idx += 1
        turn_off_led(led_channels['top'])
        turn_off_led(led_channels['middle'])
        turn_off_led(led_channels['bottom'])
        for channel in leds_step:
            turn_on_led(channel)
        time.sleep(2)
    logger.info("Stopping thread: run_leds_sequence()")


def turn_off_led(channel):
    # logger.debug("LED {} off".format(led))
    GPIO.output(channel, GPIO.LOW)


def turn_on_led(channel):
    # logger.debug("LED {} on".format(led))
    GPIO.output(channel, GPIO.HIGH)


def edit_config(cfg_type, app=None):
    """Edit a configuration file.

    The user chooses what type of config file (`cfg_type`) to edit: 'log' for
    the logging config file and 'main' for the main config file.

    The configuration file can be opened by a user-specified application (`app`)
    or a default program associated with this type of file (when `app` is None).

    Parameters
    ----------
    cfg_type : str, {'log', 'main'}
        The type of configuration file we want to edit. 'log' refers to the
        logging config file, and 'main' to the main config file used to setup a
        the Darth-Vader-RPi project such as the sound effects or the GPIO
        channels.
    app : str
        Name of the application to use for opening the config file, e.g. TextEdit
        (the default value is None which implies that the default application
        will be used to open the config file).

    Returns
    -------
    retcode : int
        If there is a `subprocess
        <https://docs.python.org/3/library/subprocess.html#subprocess.CalledProcessError>`_
        -related error, the return code is non-zero. Otherwise, it is 0 if the
        file could be successfully opened with an external program.

    """
    # Get path to user-defined config file
    filepath = get_cfg_filepath(cfg_type)
    # Command to open the config file with the default application in the
    # OS or the user-specified app, e.g. `open filepath` in macOS opens the
    # file with the default app (e.g. atom)
    default_cmd_dict = {'Darwin': 'open {filepath}',
                        'Linux': 'xdg-open {filepath}',
                        'Windows': 'cmd /c start "" "{filepath}"'}
    # NOTE: check https://bit.ly/31htaOT (pymotw) for output from
    # platform.system on three OSes
    default_cmd = default_cmd_dict.get(platform.system())
    # NOTES:
    # - `app is None` implies that the default app will be used
    # - Otherwise, the user-specified app will be used
    cmd = default_cmd if app is None else app + " " + filepath
    retcode = 1
    result = None
    try:
        # IMPORTANT: if the user provided the name of an app, it will be used as
        # a command along with the file path, e.g. `$ atom {filepath}`. However,
        # this case might not work if the user provided an app name that doesn't
        # refer to an executable, e.g. `$ TextEdit {filepath}` won't work. The
        # failed case is further processed in `except FileNotFoundError`.
        result = run_cmd(cmd.format(filepath=filepath))
        retcode = result.returncode
    except FileNotFoundError:
        # This happens if the name of the app can't be called as an executable
        # on the terminal
        # e.g. TextEdit can't be run on the terminal but atom can since the
        # latter refers to an executable.
        # To open TextEdit from the terminal, the command `open -a TextEdit`
        # must be used on macOS.
        if platform.system() == 'Darwin':
            # Get the command to open the file with the user-specified app
            # TODO: add the open commands for the other OSes
            specific_app_dict = {'Darwin': 'open -a {app}'.format(app=app)}
            cmd = specific_app_dict.get(platform.system(), app) + " " + filepath
            # TODO: explain DEVNULL, suppress stderr since we will display the
            # error
            result = run_cmd(cmd)  # stderr=subprocess.DEVNULL)
            retcode = result.returncode
    if retcode == 0:
        logger.info("Opening the {} configuration file ...".format(cfg_type))
    else:
        if result:
            err = result.stderr.decode().strip()
            logger.error(err)
    return retcode


def setup_argparser():
    # Help message that is used in various arguments
    common_help = '''Provide 'log' (without the quotes) for the logging config 
        file or 'main' (without the quotes) for the main config file.'''
    # Setup the parser
    parser = argparse.ArgumentParser(
        # usage="%(prog)s [OPTIONS]",
        prog=package_name,
        description='''\
    WRITEME''',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    # ===============
    # General options
    # ===============
    parser.add_argument("--version", action='version',
                        version='%(prog)s {}'.format(__version__))
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Enable quiet mode, i.e. nothing will be printed.")
    parser.add_argument("-s", "--simulation", action="store_true",
                        help="Enable simulation mode, i.e. SimulRPi.GPIO wil be "
                             "used for simulating RPi.GPIO.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print various debugging information, e.g. print "
                             "traceback when there is an exception.")
    # Group arguments that are closely related
    # ===========
    # Edit config
    # ===========
    edit_group = parser.add_argument_group('Edit a configuration file')
    edit_group.add_argument(
        "-e", "--edit", choices=["log", "main"],
        help="Edit a configuration file. {}".format(common_help))
    edit_group.add_argument(
        "-a", "--app-name", default=None, dest="app",
        help='''Name of the application to use for editing the file. If no 
            name is given, then the default application for opening this type of 
            file will be used.''')
    # =================
    # Reset/Undo config
    # =================
    reset_group = parser.add_argument_group(
        'Reset or undo a configuration file')
    reset_group.add_argument(
        "-r", "--reset", choices=["log", "main"],
        help='''Reset a configuration file with factory default values. 
            {}'''.format(common_help))
    reset_group.add_argument(
        "-u", "--undo", choices=["log", "main"],
        help='''Undo the LAST RESET. Thus, the config file will be restored 
            to what it was before the LAST reset. {}'''.format(common_help))
    return parser

 
def start_dv(main_cfg):
    logger.info("pygame mixer initialization")
    pygame.mixer.init()
    logger.info("RPi initialization")
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    # LEDs
    top_led = main_cfg['GPIO']['top_led']
    middle_led = main_cfg['GPIO']['middle_led']
    bottom_led = main_cfg['GPIO']['bottom_led']
    lightsaber_led = main_cfg['GPIO']['lightsaber_led']
    GPIO.setup(top_led, GPIO.OUT)
    GPIO.setup(middle_led, GPIO.OUT)
    GPIO.setup(bottom_led, GPIO.OUT)
    GPIO.setup(lightsaber_led, GPIO.OUT)
    # Buttons
    lightsaber_button = main_cfg['GPIO']['lightsaber_button']
    song_button = main_cfg['GPIO']['song_button']
    quotes_button = main_cfg['GPIO']['quotes_button']
    GPIO.setup(lightsaber_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(song_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(quotes_button, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    ### Sound
    # Create separate channel
    # Ref.: stackoverflow.com/a/59742418
    channel1 = pygame.mixer.Channel(0)  # Breathing sound
    channel2 = pygame.mixer.Channel(1)  # Song
    channel3 = pygame.mixer.Channel(2)  # Lightsaber sound
    channels = {1: channel1, 2: channel2, 3: channel3}
    # Set volume
    channels[1].set_volume(main_cfg['channel1_volume'])
    channels[2].set_volume(main_cfg['channel2_volume'])
    channels[3].set_volume(main_cfg['channel3_volume'])

    loaded_sounds = {}
    sounds_dir = os.path.expanduser(main_cfg_dict['sounds_directory'])
    logger.info("Loading sound effects...")

    def load_sounds():
        for sound_type in ['quotes', 'songs', 'sound_effects']:
            if sound_type == 'quotes':
                for quote in main_cfg_dict[sound_type]:
                    logger.info("Loading {}".format(quote['name']))
                    loaded_sounds.setdefault('quotes', [])
                    filepath = os.path.join(sounds_dir, quote['filename'])
                    channel_obj = channels[quote['channel']]
                    loaded_sounds['quotes'].append(
                        SoundWrapper(quote['name'], filepath, channel_obj))
            elif sound_type in ['songs', 'sound_effects']:
                for s in main_cfg_dict[sound_type]:
                    sound = s.popitem()
                    sound_name = sound[0]
                    sound_info = sound[1]
                    logger.info("Loading {}".format(sound[0]))
                    filepath = os.path.join(sounds_dir, sound_info['filename'])
                    channel_obj = channels[sound_info['channel']]
                    loaded_sounds.setdefault(sound_name,
                                             SoundWrapper(sound_name,
                                                          filepath,
                                                          channel_obj))
                    if sound_info.get('play'):
                        loops = sound_info.get('loops', -1)
                        loaded_sounds[sound_name].play(loops)

    load_sounds()
    quotes = loaded_sounds['quotes']

    led_channels = {'top': top_led, 'middle': middle_led, 'bottom': bottom_led}
    th = threading.Thread(target=run_led_sequence, args=(led_channels,))
    th.start()

    logger.info("")
    logger.info(msg_with_spaces("Press any button"))
    pressed_lightsaber = False
    quote_idx = 0

    try:
        while True:
            if not GPIO.input(lightsaber_button):
                logger.debug("\n\nButton {} pressed...".format(lightsaber_button))
                if pressed_lightsaber:
                    pressed_lightsaber = False
                    loaded_sounds['lightsaber_close_sound'].play()
                    time.sleep(0.3)
                    turn_off_led(22)
                else:
                    pressed_lightsaber = True
                    loaded_sounds['lightsaber_open_sound'].play()
                    loaded_sounds['lightsaber_running_sound'].play(-1)
                    time.sleep(0.3)
                    turn_on_led(lightsaber_led)
                time.sleep(0.2)
            elif not GPIO.input(song_button):
                logger.debug("\n\nButton {} pressed...".format(song_button))
                loaded_sounds['imperial_march_song'].play()
                time.sleep(0.2)
            elif not GPIO.input(quotes_button):
                logger.debug("\n\nButton {} pressed...".format(quotes_button))
                quote = quotes[quote_idx % len(quotes)]
                quote_idx += 1
                quote.play()
                time.sleep(0.2)
    except Exception as e:
        logger.exception(msg_with_spaces("Error: {}".format(e)))
        logger.info(msg_with_spaces("Exiting..."))
    except KeyboardInterrupt:
        logger.info(msg_with_spaces("Exiting..."))

    logger.info(msg_with_spaces("Cleanup..."))
    turn_off_led(top_led)
    turn_off_led(middle_led)
    turn_off_led(bottom_led)
    turn_off_led(lightsaber_led)
    GPIO.cleanup()
    th.do_run = False
    th.join()
    channel1.stop()
    channel2.stop()
    channel3.stop()

    return 0


if __name__ == '__main__':
    # Setup the default logger (whose name is __main__ since this file is run
    # as a script) which will be used for printing to the console before all
    # loggers defined in the JSON file will be configured. The printing with
    # this default logger will only be done in the cases that the user allows
    # it, e.g. the verbose option is enabled.
    # IMPORTANT: the config options need to be read before using any logger
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(levelname)-8s %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    parser = setup_argparser()
    args = parser.parse_args()

    # Load main config file
    main_cfg_filepath = get_cfg_filepath("main")
    main_cfg_dict = load_json(main_cfg_filepath)

    # Override logging configuration with command-line arguments
    retval = override_config_with_args(main_cfg_dict, parser)

    # ==============
    # Logging config
    # ==============
    # NOTE: if quiet and verbose are both activated, only quiet will have an
    # effect
    if main_cfg_dict['quiet']:
        logger.disabled = True
    else:
        # Setup logger
        logging_filepath = get_cfg_filepath("log")
        log_dict = load_json(logging_filepath)
        if main_cfg_dict['verbose']:
            keys = ['handlers', 'loggers']
            for k in keys:
                for name, val in log_dict[k].items():
                    val['level'] = "DEBUG"
            logger.info("Verbose option enabled")
        logging.config.dictConfig(log_dict)
        logger_name = "{}.{}".format(
            package_name,
            os.path.splitext(__file__)[0])
        logger = logging.getLogger(logger_name)
        msg1 = "Config options overriden by command-line arguments:\n"
        for cfg_name, old_v, new_v in retval.config_opts_overidden:
            msg1 += "{}: {} --> {}\n".format(cfg_name, old_v, new_v)
        msg2 = "Command-line arguments not found in JSON config file: " \
               "{}".format(retval.args_not_found)
        logger.debug(msg1)
        logger.debug(msg2)
    # =======
    # Actions
    # =======
    retcode = 1
    try:
        if args.edit:
            retcode = edit_config(args.edit, args.app)
        elif args.reset:
            # TODO
            # retcode = reset_config(args.reset)
            pass
        elif args.undo:
            # TODO
            # retcode = undo_config(args.undo)
            pass
        else:
            if main_cfg_dict['simulation']:
                import SimulRPi.GPIO as GPIO
                GPIO.setkeys(main_cfg_dict['key_to_channel_mapping'])
                if main_cfg_dict['quiet']:
                    GPIO.disableprinting()
                logger.info("Simulation mode enabled")
            else:
                import RPi.GPIO as GPIO
            retcode = start_dv(main_cfg_dict)
    except (AssertionError, AttributeError, KeyError, OSError) as e:
        # TODO: explain this line
        # traceback.print_exc()
        if args.verbose:
            logger.exception(e)
        else:
            logger.error(e.__repr__())
    finally:
        msg = "Program exited with {}".format(retcode)
        if retcode == 1:
            logger.error(msg)
        else:
            logger.debug(msg)
        if main_cfg_dict['quiet']:
            print()