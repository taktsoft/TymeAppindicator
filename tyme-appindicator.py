#!/usr/bin/env python
import sys
import gtk
import appindicator
import gconf
import gobject
import time

import json
import urllib
from urllib2 import Request, urlopen, URLError, HTTPError
import re
import keybinder

class TymeIndicator:
    def __init__(self):
        self.keystr = "<Ctrl>A"
        keybinder.bind(self.keystr, self.enter_new_task, "Keystring %s (user data)" % self.keystr)
        # Get the default client
        self.client = gconf.client_get_default()
        self.client.add_dir ("/apps/tyme", gconf.CLIENT_PRELOAD_NONE)

        self.ind = appindicator.Indicator("tyme-indicator", "indicator-messages", appindicator.CATEGORY_APPLICATION_STATUS)
        self.ind.set_status(appindicator.STATUS_ACTIVE)
        self.ind.set_attention_icon("new-messages-red")

        self.menu_setup()
        self.ind.set_menu(self.menu)
        self.tasks = []
        self.initialize_tyme_connector()

    def initialize_tyme_connector(self):
        print "initializing tyme connector"
        self.refresh_interval = int(self.client.get_string("/apps/tyme/refresh_interval") or 120)
        url                   = str(self.client.get_string("/apps/tyme/url"))
        authentication_token  = str(self.client.get_string("/apps/tyme/authentication_token"))
        self.tyme = TymeConnector(url, authentication_token)

    def menu_setup(self):
        self.menu = gtk.Menu()

        self.new_task_item = gtk.MenuItem("Enter new Task")
        self.new_task_item.connect("activate", self.enter_new_task)
        self.new_task_item.show()
        self.menu.append(self.new_task_item)

        self.preferences_item = gtk.MenuItem("Preferences")
        self.preferences_item.connect("activate", self.preferences)
        self.preferences_item.show()
        self.menu.append(self.preferences_item)

        self.quit_item = gtk.MenuItem("Quit")
        self.quit_item.connect("activate", self.quit)
        self.quit_item.show()
        self.menu.append(self.quit_item)

    def main(self):
        self.load_tasks()
        gtk.timeout_add(self.refresh_interval * 1000, self.refresh_tasks)
        gtk.main()

    def quit(self, widget):
        sys.exit(0)

    def preferences(self, widget):
        prefs_dialog = EditConfigValues(self.client, self.initialize_tyme_connector)

    def enter_new_task(self, widget):
        new_task_dialog = EnterNewTaskDialog(self.client, self.handle_new_task)

    def refresh_tasks(self):
        print "Refreshing"
        self.remove_old_tasks()
        self.load_tasks()
        return True

    def remove_old_tasks(self):
        for task in reversed(self.tasks):
            print "Removing " + task.description
            task.entry.destroy()

    def load_tasks(self):
        self.tasks = self.tyme.get_tasks()
        for task in reversed(self.tasks):
            print  "Adding " + task.description
            self.menu.prepend(task.to_menu_item())

    def handle_new_task(self, task_description):
        print "New task: ", task_description
        self.tyme.create_task(task_description)
        self.refresh_tasks()

class TymeConnector:
    def __init__(self, url, authentication_token):
        self.url = url
        self.authentication_token = authentication_token

    def get_tasks(self):
        req = Request(self.get_tasks_url())
        tasks = []
        try:
            body = urlopen(req).read()
            response = json.loads(body)
            for task_params in response:
                tasks.append(Task(task_params))
        except HTTPError, e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
        except URLError, e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
        except ValueError, e:
            print "URL wrong"
            print "Reason: ", e.message
        return tasks

    def create_task(self, task_description):
        try:
            data = {"task": {"name": task_description, "duration": 0, "project_id": None, "cost_target_id": None, "category_id": None, "start": time.strftime("%d.%m.%Y %X",time.gmtime())}}

            values = json.dumps(data)
            headers = {}
            headers['Content-Type'] = 'application/json'
            req = Request(self.get_tasks_url(), values, headers)
            body = urlopen(req).read()
            print body
        except HTTPError, e:
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code
        except URLError, e:
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
        except ValueError, e:
            print "URL wrong"
            print "Reason: ", e.message
        return None

    def get_tasks_url(self):
        return self.url + "/tasks.json?auth_token=" + self.authentication_token

class Task:
    def __init__(self, params):
        self.description = params['name']
        self.duration    = params['duration']
        self.entry       = None

    def to_menu_item(self):
        self.entry = gtk.MenuItem(self.description + " (" + str(self.duration) + ")")
        self.entry.set_sensitive(False)
        self.entry.show()
        return self.entry

class EnterNewTaskDialog:
    def __init__(self, client, on_success_callback):
        self.on_success_callback = on_success_callback
        self.dialog = gtk.Dialog("Tyme - Enter new Task", None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                   (gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                    gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))

        # destroy dialog on button press
        self.dialog.connect('response', self.on_close)
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)

        vbox = gtk.VBox(False, 5)
        self.dialog.vbox.pack_start(vbox)

        hbox = gtk.HBox(False, 5)
        label = gtk.Label("Task: ")
        self.entry = gtk.Entry(100)
        self.entry.set_width_chars(60)

        self.entry.connect('activate', self.on_entry_activate)

        hbox.pack_start(label, False, False, 0)
        hbox.pack_end(self.entry, False, False, 0)

        vbox.pack_start(hbox, False, False, 0)
        self.dialog.show_all()

    def on_close(self, wid, ev):
        if(ev == gtk.RESPONSE_ACCEPT):
            self.on_success_callback(self.entry.get_text())
        wid.destroy()

    def on_entry_activate(self, entry):
        self.dialog.emit('response', gtk.RESPONSE_ACCEPT)

class EditConfigValues:
    def __init__(self, client, on_close_callback):
        self.on_close_callback = on_close_callback
        self.dialog = gtk.Dialog("Tyme Preferences", None, 0, (gtk.STOCK_CLOSE, gtk.RESPONSE_ACCEPT))

        # destroy dialog on button press
        self.dialog.connect('response', self.on_close)
        self.dialog.set_default_response(gtk.RESPONSE_ACCEPT)

        vbox = gtk.VBox(False, 5)
        self.dialog.vbox.pack_start(vbox)
        hbox, entry = self.create_config_entry(client, "/apps/tyme/url", "Tyme URL", True)
        vbox.pack_start (hbox, False, False)
        hbox, entry = self.create_config_entry(client, "/apps/tyme/authentication_token", "Authentication Token")
        vbox.pack_start (hbox, False, False)
        hbox, entry = self.create_config_entry(client, "/apps/tyme/refresh_interval", "Refresh Interval")
        vbox.pack_start (hbox, False, False)
        hbox, entry = self.create_config_entry(client, "/apps/tyme/keyboard_shortcut", "Keyboard Shortcut")
        entry.connect('key-press-event', self.on_keypress)
        vbox.pack_start (hbox, False, False)
        self.dialog.show_all()

    def on_keypress(self, wid, ev):
        print wid
        print ev
        return False

    def on_close(self, wid, ev):
        self.on_close_callback()
        wid.destroy()

    # Commit changes to the GConf database. 
    def config_entry_commit(self, entry, *args):
        client = entry.get_data('client')
        text = entry.get_chars(0, -1)

        key = entry.get_data('key')

        # Unset if the string is zero-length, otherwise set
        if text:
            client.set_string(key, text)
        else:
            client.unset(key)

    # Create an entry used to edit the given config key 
    def create_config_entry(self, client, config_key, label, focus=False):
        hbox = gtk.HBox(False, 5)
        label = gtk.Label(label)
        entry = gtk.Entry()

        hbox.pack_start(label, False, False, 0)
        hbox.pack_end(entry, False, False, 0)

        # this will print an error via default error handler
        # if the key isn't set to a string

        s = client.get_string(config_key)
        if s:
            entry.set_text(s)

        entry.set_data('client', client)
        entry.set_data('key', config_key)

        # Commit changes if the user focuses out, or hits enter; we don't
        # do this on "changed" since it'd probably be a bit too slow to
        # round-trip to the server on every "changed" signal.

        entry.connect('focus_out_event', self.config_entry_commit)
        entry.connect('activate', self.config_entry_commit)    

        # Set the entry insensitive if the key it edits isn't writable.
        # Technically, we should update this sensitivity if the key gets
        # a change notify, but that's probably overkill.

        entry.set_sensitive(client.key_is_writable(config_key))

        if focus:
            entry.grab_focus()

        return (hbox, entry)


if __name__ == "__main__":
    indicator = TymeIndicator()
    indicator.main()
