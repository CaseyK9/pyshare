#!/usr/bin/env python

from string import ascii_letters, digits
from argparse import ArgumentParser
from pysftp import Connection
from subprocess import call
from random import choices
import pyperclip
import config2 as config
import sys
import os
import re

character_pool = ascii_letters + digits


def parse_arguments():
    parser = ArgumentParser()
    parser.add_argument('-m', '--mode', type=str, nargs='?',
                        help="Specify the mode. Can be 'screenshot' to open a screencap tool and upload the image or 'text' to perform an operation on the clipboard contents. Implicit if --file is specified.")
    parser.add_argument('-f', '--files', type=str, nargs='*', help='List of files to be uploaded')
    return parser.parse_args()


def generate_filename(length, ext, prefix=''):
    return prefix + ''.join(choices(character_pool, k=length)) + '.' + ext


def find_valid_filename(prefix, length, ext, conn):
    filename = generate_filename(prefix=prefix, length=length, ext=ext)
    i = 0
    while conn.exists(filename):
        filename = generate_filename(length=length, ext=ext, prefix=prefix)
        i += 1
        if i > 1000:
            # completely, definitely, totally justified recursion... yay?
            return find_valid_filename(prefix, length + 1, ext, conn)
    return filename

def upload_local_file(path: str) -> str:
    filename = ftp_upload(mode='file', sourcefile=path)[1]
    return config.url_template.format(filename)


def take_screenshot(filename: str) -> None:
    call(["escrotum", filename, "-s"])


def ftp_upload(mode='screenshot', ext=None, sourcefile=None) -> tuple:
    if ext is None:
        ext = {
            'screenshot': 'png',
            'text': 'txt',
            }.get(mode, sourcefile.rsplit('.', 1)[1])

    with Connection(config.sftp_address, username=config.username, password=config.password,
            private_key=config.private_key) as conn:
        conn.chdir(config.remote_directory)
        
        filename = find_valid_filename(prefix=config.prefix, length=config.length, ext=ext, conn=conn)
        fullpath = os.path.join(config.local_directory, filename)

        if mode == 'screenshot':
            take_screenshot(filename)
            conn.put(filename)
        elif mode == 'file':
            conn.put(sourcefile, filename)

    return fullpath, filename


def curl_upload(filename):
    if config.custom_curl_command is not None:
        return call(config.custom_curl_command)
    else:
        return call(
            f'curl -k -F"file=@{filename}" -F"name={config.username}" -F"passwd={config.password}" {config.curl_target}')



def notify_user(url):
    print(url)
    call(['notify-send', url])


def parse_clipboard(args):
        text = pyperclip.paste()
        if re.match(r'https?://', text):
            mirror_file(text)
        elif os.path.isfile(text):
            upload_local_file(text)
        else:
            upload_text(text)


def mirror_file(text):
    os.chdir(config.local_directory)
    call(['wget', text])
    filename = text.rsplit('/', 1)[1]
    url = upload_local_file(os.path.join(config.local_directory, filename))
    os.remove(os.path.join(config.local_directory, filename))
    pyperclip.copy(url)
    notify_user(url)


def upload_text(text):
    filename = generate_filename(config.length, 'txt')
    with open(os.path.join(config.local_directory, filename), 'w') as file:
        file.write(text)
    url = upload_local_file(os.path.join(config.local_directory, filename))
    #os.remove(os.path.join(config.local_directory, filename))
    pyperclip.copy(url)
    notify_user(url)


if __name__ == '__main__':
    args = parse_arguments()
    
    if config.uploader in ['ftp', 'sftp']:
        if args.files is not None:
            for file in args.files:
                upload_local_file(file) 
        elif args.mode == 'text':
            parse_clipboard(args)
        else:
            ftp_upload(mode=args.mode)
    """              
    elif args.files is not None:
       
    if config.uploader in ['ftp', 'sftp']:
        if mode != 'screenshot' and '.' in file:
            ext = '.' + file.rsplit('.', 1)[1]
        # TODO: mode file for FTP
        fullpath, filename = ftp_upload(mode, ext)
    elif config.uploader == 'curl':
        if mode=='screenshot':
            filename = generate_filename(length=config.length, ext='.png')
            fullpath = os.path.join(config.local_directory, filename)
            take_screenshot(fullpath)
        else:
            fullpath = file
        curl_upload(fullpath)
    else:
        print('Unknown mode')
        sys.exit(-1)
    url = config.url_template.format(filename)
    notify_user(url)
    """
