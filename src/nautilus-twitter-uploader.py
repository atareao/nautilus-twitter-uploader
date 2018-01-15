#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This file is part of nautilus-twitter-uploader
#
# Copyright (C) 2016 - 2018 Lorenzo Carbonell
# lorenzo.carbonell.cerezo@gmail.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#
#
import gi
try:
    gi.require_version('Gtk', '3.0')
    gi.require_version('GdkPixbuf', '2.0')
    gi.require_version('Nautilus', '3.0')
    gi.require_version('WebKit', '3.0')
except Exception as e:
    print(e)
    exit(-1)
import os
from threading import Thread
from urllib import unquote_plus
from gi.repository import GObject
from gi.repository import WebKit
from gi.repository import GdkPixbuf
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Nautilus as FileManager
from TwitterAPI import TwitterAPI
from requests_oauthlib import OAuth1Session
import json
import codecs

APP = 'nautilus-twitter-uploader'
APPNAME = 'nautilus-twitter-uploader'
ICON = 'nautilus-twitter-uploader'
VERSION = '0.1.0'
MAX_NUMBER_OF_CHARS = 280

CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config')
CONFIG_APP_DIR = os.path.join(CONFIG_DIR, APP)
TOKEN_FILE = os.path.join(CONFIG_APP_DIR, 'token')

CLIENT_ID = '9yTpnri9pnnDgrcjv56TyQADD'
CLIENT_SECTRET = 'S44foTOdsO5kY0sPYl0xTImbpoBW4F05He5uPR6O0cFku1CxhX'
REQUEST_TOKEN_URL = 'https://api.twitter.com/oauth/request_token'
ACCESS_TOKEN_URL = 'https://api.twitter.com/oauth/access_token'
AUTHORIZATION_URL = 'https://api.twitter.com/oauth/authorize'
SIGNIN_URL = 'https://api.twitter.com/oauth/authenticate'
EXTENSIONS_FROM = ['.bmp', '.eps', '.gif', '.jpg', '.pcx', '.png', '.ppm',
                   '.tif', '.tiff', '.webp']
PARAMS = {'access_token_key': '', 'access_token_secret': ''}
_ = str


class Token(object):

    def __init__(self):
        self.params = PARAMS
        self.read()

    def get(self, key):
        try:
            return self.params[key]
        except KeyError:
            self.params[key] = PARAMS[key]
            return self.params[key]

    def set(self, key, value):
        self.params[key] = value

    def read(self):
        try:
            f = codecs.open(TOKEN_FILE, 'r', 'utf-8')
        except IOError:
            self.save()
            f = open(TOKEN_FILE, 'r')
        try:
            self.params = json.loads(f.read())
        except ValueError:
            self.save()
        f.close()

    def save(self):
        if not os.path.exists(CONFIG_APP_DIR):
            os.makedirs(CONFIG_APP_DIR)
        f = open(TOKEN_FILE, 'w')
        f.write(json.dumps(self.params))
        f.close()

    def clear(self):
        self.params = PARAMS
        self.save()


class LoginDialog(Gtk.Dialog):
    def __init__(self, url, parent):
        self.code = None

        Gtk.Dialog.__init__(self, _('Login'), parent,
                            Gtk.DialogFlags.MODAL |
                            Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            (Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT,
                             Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_title(APP)
        # self.set_icon_from_file(comun.ICON)
        #
        vbox = Gtk.VBox(spacing=5)
        self.get_content_area().add(vbox)
        hbox1 = Gtk.HBox()
        vbox.pack_start(hbox1, True, True, 0)
        #
        self.scrolledwindow1 = Gtk.ScrolledWindow()
        self.scrolledwindow1.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.scrolledwindow1.set_shadow_type(Gtk.ShadowType.IN)
        hbox1.pack_start(self.scrolledwindow1, True, True, 0)
        self.hbox2 = Gtk.HBox()
        vbox.pack_start(self.hbox2, True, True, 0)
        self.hbox2.pack_start(Gtk.Label(_('Insert PIN') + ':'),
                              True,
                              True,
                              0)
        self.pincode = Gtk.Entry()
        self.hbox2.pack_start(self.pincode, True, True, 0)
        self.viewer = WebKit.WebView()
        self.scrolledwindow1.add(self.viewer)
        self.scrolledwindow1.set_size_request(600, 600)
        self.viewer.connect('navigation-policy-decision-requested',
                            self.on_navigation_requested)
        self.viewer.open(url)
        #
        self.show_all()

    # ###################################################################
    # ########################BROWSER####################################
    # ###################################################################
    def on_navigation_requested(self, view, frame, req, nav, pol):
        try:
            uri = req.get_uri()
            print('---', uri, '---')
            pos = uri.find('https://api.twitter.com/oauth/authorize')
            if pos > -1:
                self.code = uri[24:]
                # self.hide()
        except Exception as e:
            print(e)
            print('Error')

# class twitterDialog(Gtk.Dialog):


class IdleObject(GObject.GObject):
    """
    Override GObject.GObject to always emit signals in the main thread
    by emmitting on an idle handler
    """
    def __init__(self):
        GObject.GObject.__init__(self)

    def emit(self, *args):
        GLib.idle_add(GObject.GObject.emit, self, *args)


class DoItInBackground(IdleObject, Thread):
    __gsignals__ = {
        'started': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (int,)),
        'ended': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (bool,)),
        'start_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (str,)),
        'end_one': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, (float,)),
    }

    def __init__(self, elements, twitterAPI, tweet_text):
        IdleObject.__init__(self)
        Thread.__init__(self)
        self.elements = elements
        self.twitterAPI = twitterAPI
        self.tweet_text = tweet_text
        self.stopit = False
        self.ok = False
        self.daemon = True

    def stop(self, *args):
        self.stopit = True

    def send_file(self, file_in):
        tweet(self.twitterAPI, self.tweet_text, file_in)

    def run(self):
        total = 0
        for element in self.elements:
            total += get_duration(element)
        self.emit('started', total)
        try:
            self.ok = True
            for element in self.elements:
                if self.stopit is True:
                    self.ok = False
                    break
                self.emit('start_one', element)
                self.send_file(element)
                self.emit('end_one', get_duration(element))
        except Exception as e:
            print(e)
            self.ok = False
        self.emit('ended', self.ok)


class Progreso(Gtk.Dialog, IdleObject):
    __gsignals__ = {
        'i-want-stop': (GObject.SIGNAL_RUN_FIRST, GObject.TYPE_NONE, ()),
    }

    def __init__(self, title, parent, max_value):
        Gtk.Dialog.__init__(self, title, parent,
                            Gtk.DialogFlags.MODAL |
                            Gtk.DialogFlags.DESTROY_WITH_PARENT)
        IdleObject.__init__(self)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_size_request(330, 30)
        self.set_resizable(False)
        self.connect('destroy', self.close)
        self.set_modal(True)
        vbox = Gtk.VBox(spacing=5)
        vbox.set_border_width(5)
        self.get_content_area().add(vbox)
        #
        frame1 = Gtk.Frame()
        vbox.pack_start(frame1, True, True, 0)
        table = Gtk.Table(2, 2, False)
        frame1.add(table)
        #
        self.label = Gtk.Label()
        table.attach(self.label, 0, 2, 0, 1,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK,
                     yoptions=Gtk.AttachOptions.EXPAND)
        #
        self.progressbar = Gtk.ProgressBar()
        self.progressbar.set_size_request(300, 0)
        table.attach(self.progressbar, 0, 1, 1, 2,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK,
                     yoptions=Gtk.AttachOptions.EXPAND)
        button_stop = Gtk.Button()
        button_stop.set_size_request(40, 40)
        button_stop.set_image(
            Gtk.Image.new_from_stock(Gtk.STOCK_STOP, Gtk.IconSize.BUTTON))
        button_stop.connect('clicked', self.on_button_stop_clicked)
        table.attach(button_stop, 1, 2, 1, 2,
                     xpadding=5,
                     ypadding=5,
                     xoptions=Gtk.AttachOptions.SHRINK)
        self.stop = False
        self.show_all()
        self.max_value = float(max_value)
        self.value = 0.0

    def set_max_value(self, anobject, max_value):
        self.max_value = float(max_value)

    def get_stop(self):
        return self.stop

    def on_button_stop_clicked(self, widget):
        self.stop = True
        self.emit('i-want-stop')

    def close(self, *args):
        self.destroy()

    def increase(self, anobject, value):
        self.value += float(value)
        fraction = self.value / self.max_value
        self.progressbar.set_fraction(fraction)
        if self.value >= self.max_value:
            self.hide()

    def set_element(self, anobject, element):
        self.label.set_text(_('Sending: %s') % element)


class twitterDialog(Gtk.Dialog):

    def __init__(self, parent, fileimage):
        Gtk.Dialog.__init__(self,
                            _('Send images to twitter'),
                            parent,
                            Gtk.DialogFlags.MODAL |
                            Gtk.DialogFlags.DESTROY_WITH_PARENT,
                            (Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT,
                             Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL))
        self.set_icon_name(ICON)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        frame = Gtk.Frame()
        frame.set_border_width(5)
        grid = Gtk.Grid()
        grid.set_border_width(5)
        grid.set_column_spacing(5)
        grid.set_row_spacing(5)
        frame.add(grid)
        self.get_content_area().add(frame)
        label = Gtk.Label(_('Tweet') + ' :')
        label.set_xalign(0)
        grid.attach(label, 0, 0, 1, 1)
        self.tweet_length = Gtk.Label()
        grid.attach(self.tweet_length, 1, 0, 1, 1)
        scrolledwindow = Gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        scrolledwindow.set_hexpand(True)
        scrolledwindow.set_vexpand(True)
        grid.attach(scrolledwindow, 0, 1, 2, 2)
        self.tweet_text = Gtk.TextView()
        self.tweet_text.set_wrap_mode(Gtk.WrapMode.WORD)
        self.tweet_text.connect('key-release-event', self.on_insert_at_cursor)
        scrolledwindow.add(self.tweet_text)
        scrolledwindow.set_size_request(600, 60)
        label = Gtk.Label(_('Image') + ' :')
        label.set_xalign(0)
        grid.attach(label, 0, 3, 1, 1)
        # button = Gtk.Button(_('Load image'))
        # button.connect('clicked', self.on_button_clicked)
        # grid.attach(button, 1, 3, 1, 1)
        self.scrolledwindow1 = Gtk.ScrolledWindow()
        self.scrolledwindow1.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        self.scrolledwindow1.set_hexpand(True)
        self.scrolledwindow1.set_vexpand(True)
        grid.attach(self.scrolledwindow1, 0, 4, 2, 2)
        self.tweet_image = Gtk.Image()
        self.scrolledwindow1.add(self.tweet_image)
        self.scrolledwindow1.set_size_request(600, 400)

        self.load_image(fileimage)

        self.show_all()

    def update_preview_cb(self, file_chooser, preview):
        filename = file_chooser.get_preview_filename()
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(filename, 128, 128)
            preview.set_from_pixbuf(pixbuf)
            have_preview = True
        except Exception as e:
            print(e)
            have_preview = False
        file_chooser.set_preview_widget_active(have_preview)
        return

    def on_button_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(_(
            'Select one or more images to upload to Picasa Web'),
            self,
            Gtk.FileChooserAction.OPEN,
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
             Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_select_multiple(True)
        dialog.set_current_folder(os.getenv('HOME'))
        filter = Gtk.FileFilter()
        filter.set_name(_('Imagenes'))
        filter.add_mime_type('image/png')
        filter.add_mime_type('image/jpeg')
        filter.add_mime_type('image/gif')
        filter.add_mime_type('image/x-ms-bmp')
        filter.add_mime_type('image/x-icon')
        filter.add_mime_type('image/tiff')
        filter.add_mime_type('image/x-photoshop')
        filter.add_mime_type('x-portable-pixmap')
        filter.add_pattern('*.png')
        filter.add_pattern('*.jpg')
        filter.add_pattern('*.gif')
        filter.add_pattern('*.bmp')
        filter.add_pattern('*.ico')
        filter.add_pattern('*.tiff')
        filter.add_pattern('*.psd')
        filter.add_pattern('*.ppm')
        dialog.add_filter(filter)
        preview = Gtk.Image()
        dialog.set_preview_widget(preview)
        dialog.connect('update-preview', self.update_preview_cb, preview)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filenames = dialog.get_filenames()
            if len(filenames) > 0:
                self.load_image(filenames[0])
        dialog.destroy()

    def load_image(self, image):
        self.fileimage = image
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(self.fileimage)
        w = pixbuf.get_width()
        h = pixbuf.get_height()
        sw, sh = self.scrolledwindow1.get_size_request()
        zw = float(w) / float(sw)
        zh = float(h) / float(sh)
        if zw > zh:
            z = zw
        else:
            z = zh
        if z > 1:
            pixbuf = pixbuf.scale_simple(w / z, h / z,
                                         GdkPixbuf.InterpType.BILINEAR)
        print(zw, zh)
        self.tweet_image.set_from_pixbuf(pixbuf)

    def on_insert_at_cursor(self, widget, event):
        tweet_length = MAX_NUMBER_OF_CHARS - len(self.get_tweet_text())
        if tweet_length < 0:
            color = 'red'
        else:
            color = 'black'
        tweet_length = _('Chars left') + ': ' + str(tweet_length)
        tl = '<span foreground="%s">%s</span>' % (color, tweet_length)
        self.tweet_length.set_markup(tl)

    def get_tweet_text(self):
        textbuffer = self.tweet_text.get_buffer()
        return textbuffer.get_text(textbuffer.get_start_iter(),
                                   textbuffer.get_end_iter(),
                                   True)


def get_duration(file_in):
    return os.path.getsize(file_in)


def get_files(files_in):
    files = []
    for file_in in files_in:
        file_in = unquote_plus(file_in.get_uri()[7:])
        if os.path.isfile(file_in):
            files.append(file_in)
    return files


class twitterUploaderMenuProvider(GObject.GObject, FileManager.MenuProvider):

    def __init__(self):
        token = Token()
        access_token_key = token.get('access_token_key')
        access_token_secret = token.get('access_token_secret')
        if len(access_token_key) == 0 or len(access_token_secret) == 0:
            self.is_login = False
        else:
            self.is_login = True

    def all_files_are_images(self, items):
        for item in items:
            fileName, fileExtension = os.path.splitext(unquote_plus(
                item.get_uri()[7:]))
            if fileExtension.lower() not in EXTENSIONS_FROM:
                return False
        return True

    def send_images(self, menu, selected, window):
        files = get_files(selected)
        if len(files) > 0:
            if len(files) == 1:
                td = twitterDialog(window, files[0])
                if td.run() == Gtk.ResponseType.ACCEPT:
                    tweet_text = td.get_tweet_text()
                    td.destroy()
                else:
                    td.destroy()
                    return
            else:
                tweet_text = ''
            twitterAPI = oauth()
            diib = DoItInBackground(files, twitterAPI, tweet_text)
            progreso = Progreso(_('Send files to twitter'), window, len(files))
            diib.connect('started', progreso.set_max_value)
            diib.connect('start_one', progreso.set_element)
            diib.connect('end_one', progreso.increase)
            diib.connect('ended', progreso.close)
            progreso.connect('i-want-stop', diib.stop)
            diib.start()
            progreso.run()

    def login_to_twitter(self, menu, window):
        twitterAPI = oauth(window)
        if twitterAPI is not None:
            self.is_login = True
        else:
            self.is_login = False

    def unlogin_from_twitter(self, menu):
        token = Token()
        token.clear()
        self.is_login = False

    def get_file_items(self, window, sel_items):
        top_menuitem = FileManager.MenuItem(
            name='twitterUploaderMenuProvider::Gtk-twitter-top',
            label=_('Send to twitter...'),
            tip=_('Send images to twitter'))
        submenu = FileManager.Menu()
        top_menuitem.set_submenu(submenu)

        sub_menuitem_00 = FileManager.MenuItem(
            name='twitterUploaderMenuProvider::Gtk-twitter-sub-00',
            label=_('Send...'),
            tip='Send images to twitter')
        sub_menuitem_00.connect('activate', self.send_images, sel_items,
                                window)
        submenu.append_item(sub_menuitem_00)
        if self.all_files_are_images(sel_items) and self.is_login:
            sub_menuitem_00.set_property('sensitive', True)
        else:
            sub_menuitem_00.set_property('sensitive', False)
        if self.is_login:
            sub_menuitem_01 = FileManager.MenuItem(
                name='twitterUploaderMenuProvider::Gtk-twitter-sub-01',
                label=_('Unlogin from twitter'),
                tip='Unlogin from twitter')
            sub_menuitem_01.connect('activate', self.unlogin_from_twitter)
        else:
            sub_menuitem_01 = FileManager.MenuItem(
                name='twitterUploaderMenuProvider::Gtk-twitter-sub-01',
                label=_('Login to twitter'),
                tip='Login to twitter to send images')
            sub_menuitem_01.connect('activate', self.login_to_twitter, window)
        submenu.append_item(sub_menuitem_01)

        sub_menuitem_02 = FileManager.MenuItem(
            name='twitterUploaderMenuProvider::Gtk-twitter-sub-02',
            label=_('About'),
            tip=_('About'))
        sub_menuitem_02.connect('activate', self.about, window)
        submenu.append_item(sub_menuitem_02)

        return top_menuitem,

    def about(self, widget, window):
        ad = Gtk.AboutDialog(parent=window)
        ad.set_name(APPNAME)
        ad.set_version(VERSION)
        ad.set_copyright('Copyrignt (c) 2016\nLorenzo Carbonell')
        ad.set_comments(_('nautilus-twitter-uploader'))
        ad.set_license('''
This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
''')
        ad.set_website('http://www.atareao.es')
        ad.set_website_label('http://www.atareao.es')
        ad.set_authors([
            'Lorenzo Carbonell <lorenzo.carbonell.cerezo@gmail.com>'])
        ad.set_documenters([
            'Lorenzo Carbonell <lorenzo.carbonell.cerezo@gmail.com>'])
        ad.set_icon_name(ICON)
        ad.set_logo_icon_name(APPNAME)
        ad.run()
        ad.destroy()


def tweet(twitterAPI, text, image=None):
    if image is None:
        if text is None or len(text) == 0:
            return False
        try:
            r = twitterAPI.request('statuses/update', {'status': text})
            if r.status_code == 200:
                return True
        except Exception as e:
            print(e)
    else:
        file = open(image, 'rb')
        data = file.read()
        try:
            r = twitterAPI.request('statuses/update_with_media',
                                   {'status': text},
                                   {'media[]': data})
            if r.status_code == 200:
                return True
        except Exception as e:
            print(e)
    return False


def oauth(window=None):
    token = Token()
    access_token_key = token.get('access_token_key')
    access_token_secret = token.get('access_token_secret')
    if len(access_token_key) == 0 or len(access_token_secret) == 0:
        try:
            oauth_client = OAuth1Session(CLIENT_ID,
                                         client_secret=CLIENT_SECTRET,
                                         callback_uri='oob')
            resp = oauth_client.fetch_request_token(REQUEST_TOKEN_URL)
        except ValueError as e:
            print(e)
            return None
        url = oauth_client.authorization_url(AUTHORIZATION_URL)
        ld = LoginDialog(url, window)
        if ld.run() == Gtk.ResponseType.ACCEPT:
            pincode = ld.pincode.get_text()
            ld.destroy()
            if len(pincode) > 0:
                oauth_client = OAuth1Session(
                    CLIENT_ID,
                    client_secret=CLIENT_SECTRET,
                    resource_owner_key=resp.get('oauth_token'),
                    resource_owner_secret=resp.get('oauth_token_secret'),
                    verifier=pincode)
                try:
                    resp = oauth_client.fetch_access_token(ACCESS_TOKEN_URL)
                except ValueError as e:
                    print(e)
                    ld.destroy()
                    return None
                token.set('access_token_key',
                          resp.get('oauth_token'))
                token.set('access_token_secret',
                          resp.get('oauth_token_secret'))
                token.save()
                twitterAPI = TwitterAPI(CLIENT_ID,
                                        CLIENT_SECTRET,
                                        resp.get('oauth_token'),
                                        resp.get('oauth_token_secret'))
                return twitterAPI
        ld.destroy()
    else:
        twitterAPI = TwitterAPI(CLIENT_ID,
                                CLIENT_SECTRET,
                                access_token_key,
                                access_token_secret)
        return twitterAPI
    return None


if __name__ == '__main__':
    '''
    twitterAPI = oauth()
    print(twitterAPI)
    if twitterAPI is not None:
        tweet(
            twitterAPI,
            '/home/lorenzo/Escritorio/nautilus-twitter-uploader-reduced.png',
            'Test from nautilus-twitter-uploader')
    exit(1)
    '''
    image = '/home/lorenzo/Escritorio/nautilus-twitter-uploader-reduced.png'
    td = twitterDialog(None, image)
    if td.run() == Gtk.ResponseType.ACCEPT:
        print(td.get_tweet_text())
