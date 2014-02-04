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
import ConfigParser

def get_users_in_group(config, group):
    if config.has_option('groups', group):
        return [u.strip() for u in config.get("groups", group).split(",")]
    else:
        return []

def user_has_init_permission(user, conf):
    config = ConfigParser.SafeConfigParser()
    config.optionxform = str
    config.read(conf)

    # If there is no init option specified, noone will be allowed to create repositories
    if not config.has_option('system', 'init'):
        return False

    # User was not specified directly, look for groups containing it
    items = [u.strip() for u in config.get('system', 'init').split(",")]

    # If username is in items, return True immediately
    if user in items:
        return True

    groups = [n[1:] for n in items if n.startswith('@')]
    for gn in groups:
        if user in get_users_in_group(config, gn):
            # User was found in a specified group, return True
            return True

    return False

def get_permission(repository, user, conf):
    config = ConfigParser.SafeConfigParser()
    config.optionxform = str
    config.read(conf)

    reposection = 'r:' + repository

    repooptions = {}

    def check_section(section, options):
        if config.has_section(section):
            # If location has not already been set, look for it in this section
            if 'location' not in options and config.has_option(section, 'location'):
                options['location'] = config.get(section, 'location')

            # If user permissions have not already been set, look for them in this section
            if 'perms' not in options:
                if config.has_option(section, user):
                    # User was found in the repository section, use the specified permissions
                    options['perms'] = set(config.get(section, user))
                else:
                    # User was not specified directly, look for groups containing it
                    groups = [(n[1:], v) for n, v in config.items(section) if n.startswith('@')]
                    for gn, p in groups:
                        if user in get_users_in_group(config, gn):
                            # User was found in this group, add permissions from this group
                            options.setdefault('perms', set()).update(set(p))

                    # If no specific user or group permissions were found, look for "unspecified user" permissions (* =)
                    if 'perms' not in options and config.has_option(section, "default"):
                        options['perms'] = set(config.get(section, "default"))

    # First check for values in the repository's section (if it exists),
    # then check the "defaults" section for the remaining unspecified values
    check_section(reposection, repooptions)
    check_section('defaults', repooptions)

    return repooptions

def main():
    cwd = os.getcwd()
    user = sys.argv[1]
    conf = sys.argv[2]

    # Get the original SSH Command sent through. The repo should be the item after the connect string
    orig_cmd = os.getenv('SSH_ORIGINAL_COMMAND', '?')

    try:
        cmdargv = shlex.split(orig_cmd)

    # Changed to "as" here for Python 3.3 compatibility
    except ValueError as e:
        sys.stderr.write('Illegal command "%s": %s\n' % (orig_cmd, e))
        sys.exit(255)

    def get_repository(repository):
        # Now we need to extract the repository name (what is in the conf file)
        repository = repository.replace(os.sep,'',1)

        # Get the repository and users from the config file (or get a blank {})
        opts = get_permission(repository, user, conf)

        # If the returned dict is empty, then exit this process. This means no section with
        # the named repository exist!
        if 'location' not in opts:
            sys.stderr.write('No repository found for "%s"\n' % repository)
            sys.exit(255)

        # This is the reason we are using a try in case this key does not exist.
        # 'location' param under repository section contains the relative or absolute path
        # to the repository on the file system from the current working
        # directory which can be changed in the authorized_keys
        path = opts['location'].replace('$r', repository)

        # Get the path of the repository to be used with hg commands below.
        # This is the translation between the section name in the conf file and
        # the location param that points to the actual directory on the file system
        # By default, this uses cwd (Current working directory) and can be changed in the
        # authorized_keys file in the command section by using 'cd /path/to/start/from && '
        # as the first part of the command string before calling this script.
        return opts, os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))

    if cmdargv[:2] == ['hg', '-R'] and cmdargv[3:] == ['serve', '--stdio']:
        opts, repo = get_repository(cmdargv[2])

        # We will try and get the username out of the config, if it is not present, we exit!
        # We will also check to make sure the access is set to read or write. If Not, goodbye!
        if 'perms' not in opts:
            sys.stderr.write('Illegal Repository "%s"\n' % repo)
            sys.exit(255)

        perms = opts['perms']
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
        if not user_has_init_permission(user, conf):
            sys.stderr.write('User does not have permission to create repositories.\n')
            sys.exit(255)

        opts, repo = get_repository(cmdargv[2])

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
