#!/usr/bin/env python
import sys
import os
from ConfigParser import SafeConfigParser

BEGIN_COMMENT = "### HGSSH BEGIN ###"
END_COMMENT = "### HGSSH END ###"

def gen_akline(name, pubkey):
    return 

def main():
    hgssh_config_path = os.path.expanduser('~/.hgssh4.conf')
    hgssh_path = os.path.abspath(os.path.dirname(sys.argv[0]))
    hgssh_script_path = os.path.join(hgssh_path, 'hgssh4.py')
    authorized_keys_path = os.path.expanduser('~/.ssh/authorized_keys')
    
    if not os.path.isfile(hgssh_config_path):
        print "~/.hgssh4.conf not present. Run setup-hgssh4.py to set up."
        return
    
    cfg = SafeConfigParser()
    cfg.optionxform = str
    cfg.read(hgssh_config_path)

    # Get admin repository path from configuration
    admin_repository_path = cfg.get('main', 'admin-repository')
    keys_path = os.path.join(admin_repository_path, "keys")
    
    useraklines = []
    if os.path.isfile(authorized_keys_path):
        # Read existing authorized_keys file, skipping generated lines
        with open(authorized_keys_path, 'r') as f:
            in_generated_block = False
            for line in f:
                # Remove trailing spaces and linefeeds
                line = line.rstrip()

                if in_generated_block:
                    if line == END_COMMENT:
                        in_generated_block = False

                    continue
                elif line == BEGIN_COMMENT:
                    in_generated_block = True
                    continue

                useraklines.append(line)

    newaklines = []
    for root, dirs, files in os.walk(keys_path):
        for file in files:
            name, ext = os.path.splitext(file)

            if not ext == ".pub":
                continue

            with open(os.path.join(root, file), "r") as f:
                for line in f:
                    # Strip any indentation, trailing spaces or linefeeds that might have been present in the line
                    line = line.strip()

                    # Check if the line is a pubkey
                    if not line.startswith('ssh-rsa'):
                        continue

                    # Generate authorized_keys line and add it to list
                    newline = 'command="{hgssh:s} {user:s}",no-agent-forwarding,no-port-forwarding,no-pty,no-X11-forwarding {pubkey:s}'.format(
                        hgssh = hgssh_script_path,
                        user = name,
                        pubkey = line)
                    
                    newaklines.append(newline)

    # Write new authorized_keys file
    with os.fdopen(os.open(authorized_keys_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
        f.write(BEGIN_COMMENT + '\n')
        f.write('\n'.join(newaklines) + '\n')
        f.write(END_COMMENT + "\n")
        f.write('\n'.join(useraklines) + '\n')

if __name__ == '__main__':
    main()
