#!/usr/bin/env python

from string import ascii_letters, digits
from argparse import ArgumentParser
from pysftp import Connection
from subprocess import call, check_output
from random import choices
from datetime import date
from PIL import Image
import pyperclip
import config
import sys
import os
import re

character_pool = ascii_letters + digits


def parse_arguments():
    parser = ArgumentParser()
    parser.add_argument('-m' '--mode', type=str, dest='mode', default=None,
                        help='Sets the input mode. Allowed values are "screenshot" and "clipboard". Implicit it if file(s) are set.')
    parser.add_argument('-f', '--files', type=str, nargs='*', dest='files', help='List of files to be uploaded', default=None)
    parser.add_argument('-e', '--edit', type=bool, dest='edit', default=False, help='Open the screenshot in gimp to edit it before uploading')
    return parser.parse_args()


def generate_filename(length, ext):
    filename = config.prefix + ''.join(choices(character_pool, k=length)) + '.' + ext
    return filename


def get_local_full_path():
    if config.local_directory_nesting:
        folder = get_date_folder()
        return os.path.join(config.local_directory, folder)
    return config.local_directory


def get_date_folder():
    return date.today().strftime(config.local_directory_nesting)


def find_valid_filename(length, ext, conn):
    full_path = get_local_full_path()
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    filename = os.path.join(get_date_folder(), generate_filename(length=length, ext=ext))

    i = 0
    while conn.exists(filename):
        filename = os.path.join(get_date_folder(), generate_filename(length=length, ext=ext))
        i += 1
        if i > 1000:
            # completely, definitely, totally justified recursion... yay?
            return find_valid_filename(length + 1, ext, conn)
    return filename


def upload_local_file(path: str, mode='file') -> str:
    if config.uploader in ['ftp', 'sftp']:
        filename = ftp_upload(path, mode=mode)[1]
        return config.url_template.format(filename)
    else:
        notify_user(curl_upload(path))


def take_screenshot(edit=False) -> None:
    tempname = generate_filename(config.length, 'png')
    file = os.path.join(get_local_full_path(), tempname)
    call(['maim', '-suk', file])
    Image.open(file).convert('RGB').save(file)
    if edit:
        call(['gimp', file])
    upload_local_file(file, mode='screenshot')
    if not config.keep_local_copies:
        os.remove(file)


def ftp_upload(sourcefile, *, mode=None, ext=None) -> tuple:
    "This method just keeps getting worse, but I’m too afraid to actually refactor it"
    if ext is None:
        # TODO files without extension
        exts = {
            'screenshot': 'png',
            'text': 'txt',
        }
        if re.search('\.tar\.\w{1,4}', sourcefile):
            # properly handle .tar.something files
            ext = '.'.join(sourcefile.split('.')[-2:])
        else:
            ext = exts.get(mode, mode not in exts and sourcefile.split('.')[-1])  # Only do the split if necessary

    with Connection(config.sftp_address, username=config.username, password=config.password, port=config.sftp_port,
                    private_key=config.private_key, private_key_pass=config.private_key_pass) as conn:

        full_remote_dir = os.path.join(config.remote_directory, get_date_folder())
        if not conn.exists(full_remote_dir):
            conn.makedirs(full_remote_dir)
        conn.chdir(full_remote_dir)

        cur_name = sourcefile.split('/')[-1]
        filename = cur_name
        if mode == 'screenshot':
            os.chdir(get_local_full_path())
            if conn.exists(cur_name):
                filename = find_valid_filename(length=config.length, ext=ext, conn=conn)
            conn.put(filename, filename)
        else:
            filename = find_valid_filename(length=config.length, ext=ext, conn=conn)

            if mode == 'file':
                conn.put(sourcefile, filename)

        fullpath = os.path.join(get_local_full_path(), filename)

        url = config.url_template.format(os.path.join(get_date_folder(), filename))
        notify_user(url, fullpath if mode=='screenshot' else None)

    return fullpath, filename


def curl_upload(filename):
    return check_output(config.curl_command.format(filename), shell=True).decode()[:-1]


def notify_user(url, image=None):
    print(url)
    pyperclip.copy(url)
    if config.enable_thumbnails and image:
        img = Image.open(image)
        img.thumbnail((384, 384), Image.ANTIALIAS)
        thumbnail = os.path.join(config.local_directory, 'thumb.jpg')
        img.save(thumbnail)
        call(['notify-send', '-a', 'pyshare', url, '-i',  thumbnail, '-t', '3000'])
        os.remove(thumbnail)
    else:
        call(['notify-send', '-a', 'pyshare', url, '-t', '3000'])


def parse_text(args):
    text = pyperclip.paste()
    if re.match(r'(https?|s?ftp)://', text):
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
    notify_user(url)


def upload_text(text):
    filename = generate_filename(config.length, 'txt')
    with open(os.path.join(config.local_directory, filename), 'w') as file:
        file.write(text)
    url = upload_local_file(os.path.join(config.local_directory, filename))
    os.remove(os.path.join(config.local_directory, filename))
    notify_user(url)


if __name__ == '__main__':
    args = parse_arguments()
    if args.mode is None:
        if args.files is not None:
            args.mode = 'files'
        else:
            args.mode = 'screenshot'
    if args.mode == 'screenshot':
        take_screenshot(args.edit)
    elif args.mode in ('clipboard', 'text', 'b'):
        parse_text(pyperclip.paste())
    else:
        for file in args.files:
            upload_local_file(file)

    """
    if config.uploader in ['ftp', 'sftp']:
        if args.files is not None:
            for file in args.files:
                upload_local_file(file) 
        elif args.mode == 'text':
            parse_clipboard(args)
        else:
            take_screenshot()
                  
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
