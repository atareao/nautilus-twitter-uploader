#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# This file is part of nautilus-imgur-uploader
#
# Copyright (C) 2016 Lorenzo Carbonell
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
    gi.require_version('Nautilus', '3.0')
    gi.require_version('WebKit', '3.0')
except Exception as e:
    print(e)
    exit(-1)
import os
import subprocess
import shlex
import tempfile
import shutil
from threading import Thread
from urllib import unquote_plus
from gi.repository import GObject
from gi.repository import WebKit
from gi.repository import Gtk
from gi.repository import GLib
from gi.repository import Nautilus as FileManager

from imgurpython import ImgurClient
import json
import codecs
import requests

APP = 'nautilus-imgur-uploader'
APPNAME = 'nautilus-imgur-uploader'
ICON = 'nautilus-imgur-uploader'
VERSION = '0.1.0'

CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.config')
CONFIG_APP_DIR = os.path.join(CONFIG_DIR, APP)
TOKEN_FILE = os.path.join(CONFIG_APP_DIR, 'token')

CLIENT_ID = '674fadc274d0beb'
CLIENT_SECTRET = '4fd4cdcd942ca2427dbbf8f7ce6ab6ea71abb78e'
EXTENSIONS_FROM = ['.bmp', '.eps', '.gif', '.jpg', '.pcx', '.png', '.ppm',
                   '.tif', '.tiff', '.webp']
SEPARATOR = u'\u2015' * 10
PARAMS = {
        'access_token': '',
        'refresh_token': ''}
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
        self.paramas = PARAMS
        self.save()


class LoginDialog(Gtk.Dialog):
    def __init__(self, url, parent):
        self.code = None

        Gtk.Dialog.__init__(self, _('Login'), parent,
                            Gtk.DialogFlags.MODAL |
                            Gtk.DialogFlags.DESTROY_WITH_PARENT)
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
        #
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
            print(uri)
            pos = uri.find('https://localhost/?code=')
            if pos > -1:
                self.code = uri[24:]
                self.hide()
        except Exception as e:
            print(e)
            print('Error')

# class ImgurDialog(Gtk.Dialog):


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

    def __init__(self, elements, client, config=None):
        IdleObject.__init__(self)
        Thread.__init__(self)
        self.elements = elements
        self.client = client
        self.config = config
        self.stopit = False
        self.ok = False
        self.daemon = True

    def stop(self, *args):
        self.stopit = True

    def send_file(self, file_in):
        with open(file_in, 'rb') as fd:
            self.client.upload(fd, config=self.config, anon=False)

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
        fraction = self.value/self.max_value
        self.progressbar.set_fraction(fraction)
        if self.value >= self.max_value:
            self.hide()

    def set_element(self, anobject, element):
        self.label.set_text(_('Sending: %s') % element)


class ImgurDialog(Gtk.Dialog):

    def __init__(self, parent):
        Gtk.Dialog.__init__(self,
                            _('Send images to Imgur'),
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
        label = Gtk.Label(_('Name')+' :')
        label.set_xalign(0)
        grid.attach(label, 0, 0, 1, 1)
        self.name = Gtk.Entry()
        self.name.set_width_chars(50)
        grid.attach(self.name, 1, 0, 1, 1)
        label = Gtk.Label(_('Title')+' :')
        label.set_xalign(0)
        grid.attach(label, 0, 1, 1, 1)
        self.title = Gtk.Entry()
        grid.attach(self.title, 1, 1, 1, 1)
        label = Gtk.Label(_('Description')+' :')
        label.set_xalign(0)
        grid.attach(label, 0, 2, 1, 1)
        scrolledwindow = Gtk.ScrolledWindow()
        scrolledwindow.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        scrolledwindow.set_hexpand(True)
        scrolledwindow.set_vexpand(True)
        grid.attach(scrolledwindow, 0, 3, 2, 2)
        self.description = Gtk.TextView()
        scrolledwindow.add(self.description)
        self.show_all()

    def get_name(self):
        return self.name.get_text()

    def get_title(self):
        return self.title.get_text()

    def get_description(self):
        textbuffer = self.description.get_buffer()
        return textbuffer.get_text(textbuffer.get_start_iter(),
                                   textbuffer.get_end_iter(),
                                   True)


def get_duration(file_in):
    return os.path.getsize(file_in)


def get_files(files_in):
    files = []
    for file_in in files_in:
        print(file_in)
        file_in = unquote_plus(file_in.get_uri()[7:])
        if os.path.isfile(file_in):
            files.append(file_in)
    return files


class ImgurUploaderMenuProvider(GObject.GObject, FileManager.MenuProvider):

    def __init__(self):
        self.token = Token()
        self.access_token = self.token.get('access_token')
        self.refresh_token = self.token.get('refresh_token')
        if len(self.access_token) == 0 or len(self.refresh_token) == 0:
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
                imd = ImgurDialog(None)
                if imd.run() == Gtk.ResponseType.ACCEPT:
                    imd.destroy()
                    config = {
                            'album': None,
                            'name': imd.get_name(),
                            'title': imd.get_title(),
                            'description': imd.get_description()}
                else:
                    imd.destroy()
                    return
            else:
                config = None
            self.client = ImgurClient(CLIENT_ID,
                                      CLIENT_SECTRET,
                                      self.access_token,
                                      self.refresh_token)

            diib = DoItInBackground(files, self.client, config)
            progreso = Progreso(_('Send files to Imgur'), window, len(files))
            diib.connect('started', progreso.set_max_value)
            diib.connect('start_one', progreso.set_element)
            diib.connect('end_one', progreso.increase)
            diib.connect('ended', progreso.close)
            progreso.connect('i-want-stop', diib.stop)
            diib.start()
            progreso.run()

    def login_to_imgur(self, menu, window):
        client = ImgurClient(CLIENT_ID, CLIENT_SECTRET)
        authorization_url = client.get_auth_url('code')
        ld = LoginDialog(authorization_url, window)
        ld.run()
        session = requests.session()
        data = {'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECTRET,
                'code': ld.code,
                'grant_type': 'authorization_code'}
        token_url = 'https://api.imgur.com/oauth2/token'
        response = session.request('POST', token_url, data=data)
        if response is not None and response.status_code == 200 and\
                response.text is not None and len(response.text) > 0:
            ans = json.loads(response.text)
            self.access_token = ans['access_token']
            self.refresh_token = ans['refresh_token']
            token.set('access_token', access_token)
            token.set('refresh_token', refresh_token)
            token.save()
            self.is_login = True

    def unlogin_from_imgur(self, menu):
        self.token.clear()
        self.access_token = ''
        self.refresh_token = ''
        self.is_login = False

    def get_file_items(self, window, sel_items):
        top_menuitem = FileManager.MenuItem(
            name='ImgurUploaderMenuProvider::Gtk-imgur-top',
            label=_('Send to Imgur...'),
            tip=_('Send images to Imgur'))
        submenu = FileManager.Menu()
        top_menuitem.set_submenu(submenu)
        if self.all_files_are_images(sel_items):
            sub_menuitem_00 = FileManager.MenuItem(
                name='ImgurUploaderMenuProvider::Gtk-imgur-sub-00',
                label=_('Send...'),
                tip='Send images to Imgur')
            sub_menuitem_00.connect('activate', self.send_images, sel_items,
                                    window)
            submenu.append_item(sub_menuitem_00)
        if self.is_login:
            sub_menuitem_00.set_property('sensitive', True)
            sub_menuitem_01 = FileManager.MenuItem(
                name='ImgurUploaderMenuProvider::Gtk-imgur-sub-01',
                label=_('Unlogin from Imgur'),
                tip='Unlogin from Imgur')
            sub_menuitem_01.connect('activate', self.unlogin_from_imgur)
            submenu.append_item(sub_menuitem_01)
        else:
            sub_menuitem_00.set_property('sensitive', False)
            sub_menuitem_01 = FileManager.MenuItem(
                name='ImgurUploaderMenuProvider::Gtk-imgur-sub-01',
                label=_('Login to Imgur'),
                tip='Login to Imgur to send images')
            sub_menuitem_01.connect('activate', self.login_to_imgur, window)
            submenu.append_item(sub_menuitem_01)

        sub_menuitem_02 = FileManager.MenuItem(
            name='ImgurUploaderMenuProvider::Gtk-imgur-sub-02',
            label=SEPARATOR)
        submenu.append_item(sub_menuitem_02)

        sub_menuitem_03 = FileManager.MenuItem(
            name='ImgurUploaderMenuProvider::Gtk-imgur-sub-03',
            label=_('About'),
            tip=_('About'))
        sub_menuitem_03.connect('activate', self.about)
        submenu.append_item(sub_menuitem_03)

        return top_menuitem,

    def about(self, widget):
        ad = Gtk.AboutDialog()
        ad.set_name(APPNAME)
        ad.set_version(VERSION)
        ad.set_copyright('Copyrignt (c) 2016\nLorenzo Carbonell')
        ad.set_comments(_('nautilus-imgur-uploader'))
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


if __name__ == '__main__':
    '''
    import requests
    token = Token()
    access_token = token.get('access_token')
    refresh_token = token.get('refresh_token')
    if len(access_token) == 0 or len(refresh_token) == 0:
        client = ImgurClient(CLIENT_ID, CLIENT_SECTRET)
        authorization_url = client.get_auth_url('code')
        ld = LoginDialog(authorization_url, None)
        ld.run()
        session = requests.session()
        data = {'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECTRET,
                'code': ld.code,
                'grant_type': 'authorization_code'}
        token_url = 'https://api.imgur.com/oauth2/token'
        response = session.request('POST', token_url, data=data)
        if response is not None and response.status_code == 200 and\
                response.text is not None and len(response.text) > 0:
            ans = json.loads(response.text)
            access_token = ans['access_token']
            refresh_token = ans['refresh_token']
            token.set('access_token', access_token)
            token.set('refresh_token', refresh_token)
            token.save()
    client = ImgurClient(CLIENT_ID, CLIENT_SECTRET, access_token,
                         refresh_token)
    print('client', client.auth)
    config = {
            'album': None,
            'name':  'Catastrophe!',
            'title': 'Catastrophe!',
            'description': 'Cute kitten being cute on'}

    with open('/home/lorenzo/Escritorio/nautilus.jpg', 'rb') as fd:
        print(client.upload(fd, config=config, anon=False))
    '''
    imd = ImgurDialog(None)
    if imd.run() == Gtk.ResponseType.ACCEPT:
        print(imd.get_name())
        print(imd.get_title())
        print(imd.get_description())
