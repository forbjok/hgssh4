#!/usr/bin/env python
#
# Copyright 2005-2007 by Intevation GmbH <intevation@intevation.de>
#
# Author(s):
# Thomas Arendsen Hein <thomas@intevation.de>
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2 or any later version.
#
# This script is based on the original hg-ssh and also hgssh2.py and hgssh3.py
#
# hgssh4.py - modified by <chaubner@chrishaubner.com>
#

# Enable importing on demand to reduce startup time
# Please ensure the PYTHONPATH is correct to allow the site-packages
# folder that contains mercurial to be accessed so these imports work.
from mercurial import demandimport; demandimport.enable()
from mercurial import dispatch

import sys, os, shlex
from ConfigParser import SafeConfigParser

class HgSSHConfigManager(object):
    def __init__(self, configfile):
        cfg = SafeConfigParser()
        cfg.optionxform = str
        cfg.read(configfile)

        self.admin_repository_path = cfg.get('main', 'admin-repository')

        self._read_permissions_config()
        self._read_repositories_config()

    def _read_permissions_config(self):
        cfg = SafeConfigParser()
        cfg.optionxform = str
        cfg.read(os.path.join(self.admin_repository_path, 'main.conf'))

        self.groups = {}
        if cfg.has_section('groups'):
            for name, value in cfg.items('groups'):
                # Split comma-separated user list into a actual list
                self.groups[name] = [u.strip() for u in value.split(",")]

        self.init_permitted_for = []
        if cfg.has_option('system', 'init'):
            for name in [u.strip() for u in cfg.get('system', 'init').split(",")]:
                if name.startswith('@'):
                    try:
                        names = self.groups[name[1:]]
                    except KeyError:
                        continue

                    # Name is a group - add all its users with the specified permissions
                    for user in names:
                        self.init_permitted_for.append(user)
                else:
                    # Name is a user
                    self.init_permitted_for.append(name)

        if cfg.has_section('defaults'):
            self.defaults = self._parse_repository_section(cfg.items('defaults'))
        else:
            self.defaults = self._parse_repository_section([])

    def _parse_repository_section(self, items):
        location = None
        users = {}

        for name, value in items:
            # Location is special
            if name == 'location':
                location = value
                continue

            # Make a set out of permissions
            perms = set(value)

            if name.startswith('@'):
                # Name is a group - add all its users with the specified permissions
                gusers = {}

                try:
                    names = self.groups[name[1:]]
                except KeyError:
                    continue

                for user in names:
                    # If user was already specified explicitly, then that takes precedence over group permissions
                    if user in users:
                        continue

                    # Add permissions from group to user
                    gusers.setdefault(user, set()).update(perms)

                # Merge users from group into main users dict
                users.update(gusers)
            else:
                # Name is a user
                users[name] = perms

        return {'location' : location, 'users' : users}

    def _read_repositories_config(self):
        cfg = SafeConfigParser()
        cfg.optionxform = str
        cfg.read(os.path.join(self.admin_repository_path, 'repositories.conf'))

        self.repositories = {}
        for repo in cfg.sections():
            self.repositories[repo] = self._parse_repository_section(cfg.items(repo))

    def has_init_permission(self, user):
        return user in self.init_permitted_for

    def get_repository_permissions(self, user, repository):
        # First look for this specific user, then for the fallback user
        for name in [user, '?']:
            # First check repository
            try:
                return self.repositories[repository]['users'][name]
            except KeyError:
                pass

            # Then check defaults
            try:
                return self.defaults['users'][name]
            except KeyError:
                pass

        # If no permissions were found, return None
        return None

    def get_repository_location(self, repository):
        location = None

        try:
            location = self.repositories[repository]['location']
        except KeyError:
            pass

        return location or self.defaults['location']

def main():
    cwd = os.getcwd()
    user = sys.argv[1]
    hgssh_config_path = os.path.expanduser('~/.hgssh4.conf')

    # Get the original SSH Command sent through. The repo should be the item after the connect string
    orig_cmd = os.getenv('SSH_ORIGINAL_COMMAND', '?')

    try:
        cmdargv = shlex.split(orig_cmd)

    # Changed to "as" here for Python 3.3 compatibility
    except ValueError as e:
        sys.stderr.write('Illegal command "%s": %s\n' % (orig_cmd, e))
        sys.exit(255)

    # Now we need to extract the repository name (what is in the conf file)
    repository = cmdargv[2].replace(os.sep,'',1)

    # Read configuration
    config = HgSSHConfigManager(hgssh_config_path)

    def get_repository(repository):
        # No location was found for this repository
        location = config.get_repository_location(repository)
        if location == None:
            sys.stderr.write('No repository found for "%s"\n' % repository)
            sys.exit(255)

        # Replace placeholder with repository name
        path = location.replace('$r', repository)

        # Get the path of the repository to be used with hg commands below.
        # This is the translation between the section name in the conf file and
        # the location param that points to the actual directory on the file system
        # By default, this uses cwd (Current working directory) and can be changed in the
        # authorized_keys file in the command section by using 'cd /path/to/start/from && '
        # as the first part of the command string before calling this script.
        return os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))

    if cmdargv[:2] == ['hg', '-R'] and cmdargv[3:] == ['serve', '--stdio']:
        repo = get_repository(repository)

        # Get the user's permissions for this repository
        perms = config.get_repository_permissions(user, repository)

        # If no permissions were found for this user and repository, do not allow access
        if perms == None:
            sys.stderr.write('Illegal Repository "%s"\n' % repository)
            sys.exit(255)

        # If the user does not have read or write (write implies read) we exit.
        if not len(perms.intersection(["r", "w"])) > 0:
            sys.stderr.write('Access denied to "%s"\n' % repository)
            sys.exit(255)

        cmd = ['-R', repo, 'serve', '--stdio']
        if 'w' not in perms:
            cmd += [
                '--config',
                'hooks.prechangegroup.hg-ssh=python:__main__.rejectpush',
                '--config',
                'hooks.prepushkey.hg-ssh=python:__main__.rejectpush'
                ]

        dispatch.dispatch(dispatch.request(cmd))
    elif cmdargv[:2] == ['hg', 'init']:
        if not config.has_init_permission(user):
            sys.stderr.write('User does not have permission to create repositories.\n')
            sys.exit(255)

        repo = get_repository(repository)

        dispatch.dispatch(dispatch.request(['init', repo]))
    else:
        sys.stderr.write('Illegal command "%s"\n' % orig_cmd)
        sys.exit(255)

def rejectpush(ui, **kwargs):
    ui.warn("Permission denied\n")
    # mercurial hooks use unix process conventions for hook return values
    # so a truthy return means failure
    return True

if __name__ == '__main__':
    main()
