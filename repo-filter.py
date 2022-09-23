import click
import os
import shutil
from distutils.dir_util import copy_tree
import stat
import git
import git_filter_repo as fr
import subprocess
from pick import pick

def rmtree(top):
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            filename = os.path.join(root, name)
            os.chmod(filename, stat.S_IWUSR)
            os.remove(filename)
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(top)

def fixup_commits(commit, metadata):
    if len(commit.parents) == 0:
        files = ['README.md', 'load.go', 'InsertEnvLoad.exe', '.github/workflows/releaser.yml']

        for file in files:
            fhash = subprocess.check_output(['git', 'hash-object', '-w', file]).strip()
            fmode = b'100755' if os.access(file, os.X_OK) else b'100644'

            commit.file_changes.append(fr.FileChange(b'M', os.fsencode(file), fhash, fmode))

@click.command()
@click.argument('binaryname', required=True, type=click.Choice(['automuteus', 'galactus'], case_sensitive=False))
@click.argument('dest', required=True, type=click.Path(file_okay=False, resolve_path=True))
def filter(binaryname, dest):
    """Filter the original repository in order to make it able to build for AutoMuteUs Portable."""
    try:
        # If specified directory already exists, prompt to delete it
        if os.path.isdir(dest):
            click.echo('Specified directory already exists')
            if click.confirm('Do you want me to delete the directory and continue to run?'):
                rmtree(dest)
            else:
                return

        upstream_url = f'git@github.com:automuteus/{binaryname}'

        # Clone the repository
        repo = git.Repo.clone_from(upstream_url, dest)

        # Set up the remotes
        origin_url = f'git@github.com:AutoMuteUs-Portable/{binaryname}'
        repo.remotes.origin.rename('upstream')
        origin = repo.create_remote('origin', origin_url)

        # Rename the branch from `master` to `main`
        if 'master' in repo.heads:
            repo.heads.master.rename('main')
        elif 'main' not in repo.heads:
            raise Exception('Failed to recognize the master(or main) branch')

        # Move to the repository
        os.chdir(dest)

        # Delete some files from the repository
        fr_args = fr.FilteringOptions.parse_args([
            '--invert-paths',
            '--path', 'README.md',
            '--path', '.github/workflows',
            '--force'
        ])
        filter = fr.RepoFilter(fr_args)
        filter.run()

        # Copy the files to the repository
        base_path = os.path.dirname(__file__)

        copy_tree(os.path.join(base_path, binaryname), dest)
        
        os.chdir(dest)
        # Add the files to the repository
        fr_args = fr.FilteringOptions.parse_args([
            '--preserve-commit-encoding',
            '--replace-refs', 'update-no-add',
            '--force'
        ])
        filter = fr.RepoFilter(fr_args, commit_callback=fixup_commits)
        filter.run()

        # Push the repository
        origin.push(force=True).raise_if_error()

        # Retrieve the tags
        tags = reversed(sorted(repo.tags, key=lambda t: t.commit.committed_date))
        tagNames = list(map(lambda t: t.name, tags))

        selected_tagNames = pick(tagNames, 'Please choose the tags that you want to push', multiselect=True)
        selected_tags = [repo.tags[name] for name, _ in selected_tagNames]
        selected_tags.sort(key=lambda t: t.commit.committed_date)

        # Push the selected tags
        for tag in selected_tags:
            origin.push(tag, force=True).raise_if_error()
            click.echo(f'Pushed the tag `{tag.name}`')

            input('Press Enter to continue...')
        
        # Close the repository
        repo.close()
    except Exception as err:
        click.echo(err)
        return

if __name__ == '__main__':
    filter()