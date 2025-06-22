import argparse
import logging
import os
import sys
import time

try:
    import psutil
except ImportError:
    print("Error: psutil is not installed. Please install it using 'pip install psutil'")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define browser extension directories (platform-specific)
CHROME_EXTENSIONS_DIR_WINDOWS = os.path.join(os.environ['LOCALAPPDATA'], 'Google', 'Chrome', 'User Data', 'Default', 'Extensions')
CHROME_EXTENSIONS_DIR_LINUX = os.path.expanduser("~/.config/google-chrome/Default/Extensions")
CHROME_EXTENSIONS_DIR_MAC = os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Extensions")


FIREFOX_EXTENSIONS_DIR_WINDOWS = os.path.join(os.environ['APPDATA'], 'Mozilla', 'Firefox', 'Profiles') # requires profile parsing
FIREFOX_EXTENSIONS_DIR_LINUX = os.path.expanduser("~/.mozilla/firefox")  #requires profile parsing
FIREFOX_EXTENSIONS_DIR_MAC = os.path.expanduser("~/Library/Application Support/Firefox/Profiles") # requires profile parsing



def setup_argparse():
    """Sets up the command line argument parser."""
    parser = argparse.ArgumentParser(description='Monitor browser extensions for changes.')
    parser.add_argument('--browser', type=str, choices=['chrome', 'firefox'],
                        help='The browser to monitor (chrome or firefox).', required=False)
    parser.add_argument('--interval', type=int, default=60,
                        help='The interval (in seconds) between checks.', required=False)
    parser.add_argument('--report', type=str,
                        help='File to save extension change reports.', required=False)
    parser.add_argument('--alert-on-change', action='store_true', help='Alert and log on extension change')
    parser.add_argument('--extensions_dir', type=str, help='Specify the extensions directory', required=False)
    return parser.parse_args()

def get_chrome_extensions(extensions_dir):
    """Gets a list of Chrome extensions by listing directories in the extensions directory."""
    try:
        if not os.path.exists(extensions_dir):
             logging.warning(f"Chrome extensions directory not found: {extensions_dir}")
             return []

        extensions = [d for d in os.listdir(extensions_dir) if os.path.isdir(os.path.join(extensions_dir, d))]
        logging.debug(f"Found chrome extensions: {extensions}")
        return extensions
    except OSError as e:
        logging.error(f"Error accessing Chrome extensions directory: {e}")
        return []


def get_firefox_extensions(extensions_dir):
    """
    Gets the installed extensions from Firefox profile directories.
    Note: This is a simplified implementation and needs more robust profile parsing for real-world scenarios.
    """
    try:
        if not os.path.exists(extensions_dir):
            logging.warning(f"Firefox profiles directory not found: {extensions_dir}")
            return []

        extensions = []
        for item in os.listdir(extensions_dir):
            profile_path = os.path.join(extensions_dir, item)
            if os.path.isdir(profile_path) and item.endswith(".default-release"): #Basic filter
                extensions_json = os.path.join(profile_path, "extensions.json") #Attempt to read extensions file, needs more sophisticated parsing

                if os.path.exists(extensions_json): #Check if extensions.json exists before opening
                    try:
                        with open(extensions_json, "r") as file:
                            extensions_data = file.read() # Read the file, needs more sophisticated parsing such as json.load
                            logging.debug(f"Found extensions file in profile: {item}")
                            extensions.append(item) # Add the profile directory containing extensions.json as an extension
                    except (FileNotFoundError, IOError) as e:
                        logging.error(f"Error reading extensions.json: {e}")

        logging.debug(f"Found Firefox profiles with extensions: {extensions}")
        return extensions
    except OSError as e:
        logging.error(f"Error accessing Firefox profiles directory: {e}")
        return []



def main():
    """Main function to monitor browser extensions."""
    args = setup_argparse()

    # Validate input
    if args.interval <= 0:
        logging.error("Interval must be a positive integer.")
        sys.exit(1)
    if args.report and not args.report.endswith(".txt"):
         logging.warning("Report file should end with .txt extension")


    browser = args.browser
    interval = args.interval
    report_file = args.report
    alert_on_change = args.alert_on_change

    if args.extensions_dir:
        extensions_dir = args.extensions_dir
    else:
        if browser == 'chrome':
            if os.name == 'nt':
                extensions_dir = CHROME_EXTENSIONS_DIR_WINDOWS
            elif os.name == 'posix':
                extensions_dir = CHROME_EXTENSIONS_DIR_LINUX
            elif os.name == 'darwin':
                extensions_dir = CHROME_EXTENSIONS_DIR_MAC
            else:
                logging.error("Unsupported OS. Please specify the extensions directory using --extensions_dir.")
                sys.exit(1)

        elif browser == 'firefox':
            if os.name == 'nt':
                extensions_dir = FIREFOX_EXTENSIONS_DIR_WINDOWS
            elif os.name == 'posix':
                extensions_dir = FIREFOX_EXTENSIONS_DIR_LINUX
            elif os.name == 'darwin':
                extensions_dir = FIREFOX_EXTENSIONS_DIR_MAC
            else:
                logging.error("Unsupported OS. Please specify the extensions directory using --extensions_dir.")
                sys.exit(1)
        else:
            logging.error("Please specify a browser (--browser) or extensions directory (--extensions_dir).")
            sys.exit(1)

    if browser == 'chrome':
        get_extensions = get_chrome_extensions
    elif browser == 'firefox':
        get_extensions = get_firefox_extensions
    else:
        logging.error("Invalid browser specified.")
        sys.exit(1)


    previous_extensions = set(get_extensions(extensions_dir))

    logging.info(f"Monitoring {browser} extensions directory: {extensions_dir} every {interval} seconds.")

    try:
        while True:
            current_extensions = set(get_extensions(extensions_dir))

            added_extensions = current_extensions - previous_extensions
            removed_extensions = previous_extensions - current_extensions

            if added_extensions or removed_extensions:
                logging.info("Extension changes detected!")

                if added_extensions:
                    logging.info(f"Added extensions: {added_extensions}")
                if removed_extensions:
                    logging.info(f"Removed extensions: {removed_extensions}")

                if alert_on_change:
                    if added_extensions:
                        print(f"Alert: Added extensions: {added_extensions}")
                    if removed_extensions:
                        print(f"Alert: Removed extensions: {removed_extensions}")


                if report_file:
                    try:
                        with open(report_file, 'a') as f:
                            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}: Extension changes detected:\n")
                            if added_extensions:
                                f.write(f"  Added: {added_extensions}\n")
                            if removed_extensions:
                                f.write(f"  Removed: {removed_extensions}\n")
                            f.write("\n")
                        logging.info(f"Extension changes written to report file: {report_file}")
                    except IOError as e:
                        logging.error(f"Error writing to report file: {e}")

            previous_extensions = current_extensions
            time.sleep(interval)

    except KeyboardInterrupt:
        logging.info("Monitoring stopped.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # Usage Examples:
    # 1. Monitor Chrome extensions every 60 seconds, reporting changes to chrome_report.txt
    #    python main.py --browser chrome --interval 60 --report chrome_report.txt
    # 2. Monitor Firefox extensions and alert on any changes.
    #    python main.py --browser firefox --alert-on-change
    # 3. Monitor Chrome extensions with a specific extensions directory:
    #    python main.py --browser chrome --extensions_dir "/path/to/chrome/extensions"
    main()