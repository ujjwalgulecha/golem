import sys
from codecs import open
from os import listdir, path, walk, makedirs
from sys import platform

import semantic_version
from setuptools import find_packages, Command
from setuptools.command.test import test

from golem.core.common import get_golem_path, is_windows, is_osx, is_linux
from gui.view.generateui import generate_ui_files


class PyTest(test):
    """
    py.test integration with setuptools,
    https://pytest.org/latest/goodpractises.html\
    #integration-with-setuptools-test-commands
    """

    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        test.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        test.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        import sys
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


class PyInstaller(Command):
    description = "run pyinstaller and packaging actions"
    user_options = [
        ('package-path=', None, 'save generated gzipped tarball at this path'),
    ]

    def initialize_options(self):
        self.package_path = None

    def finalize_options(self):
        pass

    def run(self):
        import subprocess
        import shutil

        build_dir = path.join('build')
        dist_dir = path.join('dist')

        for directory in [build_dir, dist_dir]:
            if path.exists(directory):
                shutil.rmtree(directory)

        for spec in ['golemapp.spec', 'golemcli.spec']:
            self.banner("Building {}".format(spec))
            subprocess.check_call([
                sys.executable, '-m', 'PyInstaller', '--clean',
                '--win-private-assemblies', spec
            ])

        print("> Copying taskcollector")
        self.copy_taskcollector(dist_dir)

        print("> Copying examples")
        self.copy_examples(dist_dir)

        print("> Copying chain")
        self.copy_chain(dist_dir)

        print("> Compressing distribution")
        archive_dir = self.move(dist_dir)
        archive_file = self.compress(archive_dir, dist_dir)
        print("> Archive saved: '{}'".format(archive_file))

    def banner(self, msg):
        print("\n> --------------------------------")
        print("> {}".format(msg))
        print("> --------------------------------\n")

    def copy_taskcollector(self, dist_dir):
        import shutil

        taskcollector_dir = path.join(
            'apps',
            'rendering',
            'resources',
            'taskcollector',
            'x64' if is_windows() else '',
            'Release'
        )
        shutil.copytree(taskcollector_dir,
                        path.join(dist_dir, taskcollector_dir))

    def copy_chain(self, dist_dir):
        from shutil import copy
        from os import makedirs

        chain_files = path.join('golem', 'ethereum', 'rinkeby.json')
        dist_dir = path.join(dist_dir, 'golem', 'ethereum')
        makedirs(dist_dir)
        copy(chain_files, dist_dir)

    def copy_examples(self, dist_dir):
        import shutil

        examples_dir = path.join(dist_dir, 'examples')
        blender_dir = path.join(examples_dir, 'blender')
        lux_dir = path.join(examples_dir, 'lux')

        blender_example = path.join('apps', 'blender', 'benchmark',
                                    'test_task', 'bmw27_cpu.blend')
        lux_example = path.join('apps', 'lux', 'benchmark', 'test_task')

        if not path.exists(blender_dir):
            makedirs(blender_dir)

        shutil.copy(blender_example, blender_dir)
        shutil.copytree(lux_example, lux_dir)

    def move(self, dist_dir):
        import shutil

        version = get_version()
        ver_dir = path.join(dist_dir, 'golem-{}'.format(version))

        if not path.exists(ver_dir):
            makedirs(ver_dir)

        shutil.move(path.join(dist_dir, 'apps'), ver_dir)
        shutil.move(path.join(dist_dir, 'examples'), ver_dir)
        shutil.move(path.join(dist_dir, 'golem'), ver_dir)
        if is_windows():
            shutil.move(path.join(dist_dir, 'golemapp.exe'), ver_dir)
            shutil.move(path.join(dist_dir, 'golemcli.exe'), ver_dir)
        else:
            shutil.move(path.join(dist_dir, 'golemapp'), ver_dir)
            shutil.move(path.join(dist_dir, 'golemcli'), ver_dir)

        return ver_dir

    def compress(self, src_dir, dist_dir):
        archive_file = self.get_archive_path(dist_dir)
        if not is_windows():
            import tarfile

            with tarfile.open(archive_file, "w:gz") as tar:
                tar.add(src_dir, arcname=path.basename(src_dir))
        else:
            import zipfile
            zf = zipfile.ZipFile(archive_file, "w")
            for dirname, _, files in walk(src_dir):
                zf.write(dirname)
                for filename in files:
                    zf.write(path.join(dirname, filename))
            zf.close()
        return archive_file

    def get_archive_path(self, dist_dir):
        if self.package_path:
            return self.package_path

        extension = 'tar.gz'
        if is_osx():
            sys_name = 'macos'
        elif is_linux():
            sys_name = 'linux_x64'
        elif is_windows():
            sys_name = 'win32'
            extension = 'zip'
        else:
            raise EnvironmentError("Unsupported OS: {}".format(sys.platform))

        version = get_version()
        return path.join(dist_dir,
                         'golem-{}-{}.{}'.format(sys_name, version, extension))


def get_long_description(my_path):
    """
    Read readme file
    :return: Content of the README file
    """
    with open(path.join(my_path, 'README.md'), encoding='utf-8') as f:
        read = f.read()
    return read


def find_required_packages():
    if platform.startswith('darwin'):
        return find_packages(exclude=['examples', 'tests'])
    return find_packages(include=['golem*', 'apps*', 'gui*'])


def parse_requirements(my_path):
    """
    Parse requirements.txt file
    :return: [requirements, dependencies]
    """
    import re
    requirements = []
    dependency_links = []
    for line in open(path.join(my_path, 'requirements.txt')):
        line = line.strip()
        if line.startswith('-') or line.startswith('#'):
            continue

        m = re.match('.+#egg=(?P<package>.+)$', line)
        if m:
            requirements.append(m.group('package'))
            dependency_links.append(line)
        else:
            requirements.append(line)
    return requirements, dependency_links


def print_errors(*errors):
    for error in errors:
        if error:
            print(error)


def generate_ui():
    try:
        generate_ui_files()
    except EnvironmentError as err:
        return \
            """
            ***************************************************************
            Generating UI elements was not possible.
            Golem will work only in command line mode.
            Generate_ui_files function returned {}
            ***************************************************************
            """.format(err)


def update_variables():
    import re
    file_ = path.join(get_golem_path(), 'golem', 'core', 'variables.py')
    with open(file_, 'r') as f_:
        variables = f_.read()
    version = get_version()
    variables = re.sub('APP_VERSION = .*',
                       'APP_VERSION = "{}"'.format(version), variables)
    with open(file_, 'w') as f_:
        f_.write(variables)


# @todo do we really need it?
def move_wheel():
    from shutil import move
    path_ = path.join(get_golem_path(), 'dist')
    files_ = [f for f in listdir(path_) if path.isfile(path.join(path_, f))]
    files_.sort()
    source = path.join(path_, files_[-1])
    dst = path.join(path_, file_name())
    move(source, dst)


def get_version():
    from git import Repo
    tags = Repo(get_golem_path()).tags
    versions = []

    for tag in tags:
        if not tag.is_valid:
            continue
        try:
            semantic_version.Version(tag.name)
            versions.append(tag.name)
        except Exception as exc:
            print("Tag {} is not a valid release version: {}".format(
                  tag, exc))

    if not versions:
        raise EnvironmentError("No git version tag found "
                               "in the repository")
    return sorted(versions)[-1]


def file_name():
    """
    Get wheel name
    :return: Name for wheel
    """
    from git import Repo
    repo = Repo(get_golem_path())
    tag = repo.tags[-2]  # get latest tag
    tag_id = tag.commit.hexsha  # get commit id from tag
    commit_id = repo.head.commit.hexsha  # get last commit id
    if platform.startswith('linux'):
        from platform import architecture
        if architecture()[0].startswith('64'):
            plat = "linux_x86_64"
        else:
            plat = "linux_i386"
    elif platform.startswith('win'):
        plat = "win32"
    elif platform.startswith('darwin'):
        plat = "macosx_10_12_x86_64"
    else:
        raise SystemError("Incorrect platform: {}".format(platform))
    if commit_id != tag_id:  # devel package
        return "golem-{}-0x{}{}-cp35-none-{}.whl".format(tag.name,
                                                         commit_id[:4],
                                                         commit_id[-4:],
                                                         plat)
    else:  # release package
        return "golem-{}-cp35-none-{}.whl".format(tag.name, plat)


def get_files():
    golem_path = get_golem_path()
    extensions = ['py', 'pyc', 'pyd', 'ini', 'template', 'dll', 'png', 'txt']
    excluded = ['golem.egg-info', 'build', 'tests', 'Installer', '.git']
    beginnig = "../../golem/"
    result = []
    for root, dirs, files in walk('.', topdown=False):
        if root != '.' and root.split(path.sep)[1] in excluded:
            continue
        srcs = []
        if root == '.':
            dst = path.normpath(
                path.join("../..", root.replace(golem_path, '')))
        else:
            dst = path.normpath(
                path.join(beginnig, root.replace(golem_path, '')))
        for name in files:
            f_ = "{}/{}".format(root, name)
            if f_.split('.')[-1] in extensions:
                srcs.append(path.normpath(f_.replace(golem_path, '')))
        if len(srcs) > 0:
            result.append((dst, srcs))
    return result
