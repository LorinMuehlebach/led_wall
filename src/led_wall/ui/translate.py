# Import gettext module
import pathlib 
import gettext

def setup_translate():
    filepath = pathlib.Path('__file__').resolve()
    # Set the local directory
    appname = 'led_wall'
    localedir = filepath/'locales'

    # Set up Gettext
    en_i18n = gettext.translation(appname, localedir, fallback=True, languages=['de'])

    # Create the "magic" function
    en_i18n.install()

    return en_i18n.gettext