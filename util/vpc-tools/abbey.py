#!/usr/bin/env python

import sys
from argparse import ArgumentParser
import subprocess

try:
    import boto.ec2
    from boto.vpc import VPCConnection
    from boto.exception import EC2ResponseError
except ImportError:
    print "boto required for script"
    sys.exit(1)

def run_cmd(cmd):
    if args.noop:
        sys.stderr.write('would have run: {}\n\n'.format(cmd))
    else:
        sys.stderr.write('running: {}\n'.format(cmd))
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=True)
        # don't buffer output
        for line in iter(process.stdout.readline, ""):
            sys.stderr.write(line)
            sys.stderr.flush()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument('--noop', action='store_true',
                        help="don't actually run the cmds",
                        default=False)
    parser.add_argument('--secure-vars', required=False,
                        metavar="SECURE_VAR_FILE",
                        help="path to secure-vars, defaults to "
                        "../../../configuration-secure/ansible/"
                        "vars/DEPLOYMENT/ENVIRONMENT.yml")
    parser.add_argument('--stack-name',
                        help="defaults to DEPLOYMENT-ENVIRONMENT",
                        metavar="STACK_NAME",
                        required=False)
    parser.add_argument('-p', '--play', metavar="PLAY", required=True)
    parser.add_argument('-d', '--deployment', metavar="DEPLOYMENT",
                        required=True)
    parser.add_argument('-e', '--environment', metavar="ENVIRONMENT",
                        required=True)
    parser.add_argument('-v', '--vars', metavar="EXTRA_VAR_FILE",
                        help="path to extra var file", required=False)
    parser.add_argument('-a', '--application', required=False,
                        help="Application for subnet, defaults to admin",
                        default="admin")
    parser.add_argument('--configuration-hash', required=False,
                        help="configuration repo version",
                        default="master")
    parser.add_argument('--configuration-secure-hash', required=False,
                        help="configuration-secure repo version",
                        default="master")
    parser.add_argument('-j', '--jenkins-build', required=False,
                        help="jenkins build number to update")
    parser.add_argument('-b', '--base-ami', required=False,
                        help="ami to use as a base ami",
                        default="ami-d0f89fb9")
    parser.add_argument('-i', '--identity', required=False,
                        help="path to identity file for pulling down configuration-secure")
    parser.add_argument('-r', '--region', required=False,
                        default="us-east-1",
                        help="aws region")
    parser.add_argument('-k', '--keypair', required=False,
                        default="deployment",
                        help="AWS keypair to use for instance")
    parser.add_argument('-t', '--instance-type', required=False,
                        default="m1.large",
                        help="instance type to launch")
    parser.add_argument("--security-group", required=False,
                        default="abbey", help="Security group to use")
    return parser.parse_args()


def main():

    security_group_id = None

    ec2 = boto.ec2.connect_to_region(args.region)
    grp_details = ec2.get_all_security_groups()
    for grp in grp_details:
        if grp.name == args.security_group:
            security_group_id = grp.id
            break
    if not security_group_id:
        print "Unable to lookup id for security group {}".format(args.security_group)
        sys.exit(1)

    print "{:22} {:22}".format("stack_name", stack_name)
    for value in ['region', 'base_ami', 'keypair', 'instance_type', 'security_group']:
        print "{:22} {:22}".format(value, getattr(args, value))

    vpc = VPCConnection()
    subnet = vpc.get_all_subnets(
        filters={
            'tag:aws:cloudformation:stack-name': stack_name,
            'tag:Application': args.application}
    )
    if len(subnet) != 1:
        sys.stderr.write("ERROR: Expected 1 admin subnet, got {}\n".format(
            len(subnet)))
        sys.exit(1)
    subnet_id = subnet[0].id

    print "{:22} {:22}".format("subnet_id", subnet_id)

    ec2_args = {
        'security_group_ids': [security_group_id],
        'subnet_id': subnet_id,
        'key_name': args.keypair,
        'image_id': args.base_ami,
        'instance_type': args.instance_type,
    }

    res = ec2.run_instances(**ec2_args)

    user_data = """

    base_dir="/var/tmp/edx-cfg"
    extra_vars="/var/tmp/extra-vars-$$.yml"
    secure_identity="/var/tmp/config-secure-git-ident"

    cat << EOF >> /var/tmp/git_ssh.sh
    #!/bin/sh
    exec /usr/bin/ssh -o StrictHostKeyChecking=no -i "$secure_identity" "\$@"
    EOF

    cat << EOF >> $secure_identity
    {secure_identity}
    EOF

    mkdir -p $base_dir
    cd /var/tmp/$base_dir
    if [[ -d $base_dir/configuration/.git ]]; then
        cd $base_dir/configuration
        git reset --hard {configuration_hash }
    else
        cd $base_dir
        git clone -b {configuration_hash} https://github.com/edx/configuration
    fi

    if [[ -d $base_dir/configuration-secure/.git ]]; then
        cd $base_dir/configuration-secure
        git reset --hard {configuration_secure_hash}
    else
        cd $base_dir
        git clone -b {configuration_secure_hash} https://github.com/edx/configuration-secure
    fi

    cd $base_dir/configuration
    sudo pip install -r requirements.txt

    cd $base_dir/configuration/playbooks/edx-east
    cat << EOF >> $extra_vars
    {extra_vars}
    EOF


    ansible-playbook -c local {play} -e@/var/tmp/extra-vars-$$

    rm -f $extra_vars
    """




if __name__ == '__main__':

    args = parse_args()
    if args.secure_vars:
        secure_vars = args.secure_vars
    else:
        secure_vars = "../../../configuration-secure/" \
                      "ansible/vars/{}/{}.yml".format(
                      args.deployment, args.environment)
    if args.stack_name:
        stack_name = args.stack_name
    else:
        stack_name = "{}-{}".format(args.environment, args.deployment)
    main()
