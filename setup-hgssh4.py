#!/usr/bin/env python
import sys
import os
from ConfigParser import SafeConfigParser

from mercurial import demandimport; demandimport.enable()
from mercurial import dispatch

def main():
    hgssh_config_path = os.path.expanduser("~/.hgssh4.conf")
    hgssh_path = os.path.abspath(os.path.dirname(sys.argv[0]))
    hgssh_refresh_script_path = os.path.join(hgssh_path, 'gen-authorizedkeys.py')
    hgssh_repos_path = os.path.expanduser("~/repositories")
    
    if os.path.isfile(hgssh_config_path):
        print '~/.hgssh4.conf already exists.'
        return
    
    admin_repo_name = "hgssh4-admin"
    admin_repo_path = os.path.join(hgssh_repos_path, admin_repo_name)
    
    print 'Initializing admin repository...'
    dispatch.dispatch(dispatch.request(['init', admin_repo_path]))
    
    print 'Generating initial configuration...'
    permsconf = os.path.join(admin_repo_path, 'main.conf')
    reposconf = os.path.join(admin_repo_path, 'repositories.conf')
    hgrcpath = os.path.join(admin_repo_path, '.hg', 'hgrc')
    
    # Generate .hgssh4.conf
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.add_section('main')
    cfg.set('main', 'admin-repository', admin_repo_path)
    
    with open(hgssh_config_path, 'w') as f:
        cfg.write(f)

    # Generate main config
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.add_section('groups')
    cfg.add_section('system')
    cfg.add_section('defaults')
    cfg.set('groups', 'admins', '')
    cfg.set('system', 'init', '@admins')
    cfg.set('defaults', 'location', os.path.join(hgssh_repos_path, '$r'))
    cfg.set('defaults', '@admins', 'rw')
    
    with open(permsconf, "w") as f:
        cfg.write(f)
    
    # Generate repositories config
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.add_section(admin_repo_name)
    cfg.set(admin_repo_name, 'location', admin_repo_path)
    cfg.set(admin_repo_name, '@admins', 'rw')
    
    with open(reposconf, 'w') as f:
        cfg.write(f)
    
    # Generate hgrc
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.add_section('hooks')
    cfg.set('hooks', 'changegroup.update', 'hg update -C')
    cfg.set('hooks', 'changegroup.refresh', hgssh_refresh_script_path)
    cfg.set('hooks', 'commit.refresh', hgssh_refresh_script_path)
    
    with open(hgrcpath, 'w') as f:
        cfg.write(f)
    
    # Create key directory and put dummy file there so it will be added
    keys_path = os.path.join(admin_repo_path, 'keys')
    os.makedirs(keys_path)
    open(os.path.join(keys_path, 'PUT_USER_KEYS_HERE'), 'w').close()
    
    # Commit initial configuration to admin repository
    os.chdir(admin_repo_path)
    dispatch.dispatch(dispatch.request(['commit', '-A', '-m', 'initial configuration', '-u', 'install']))

if __name__ == '__main__':
    main()
