"""TEMPLATE – copy this file to a name without the leading underscore
(for example my_tools.py), edit it, then choose Plugins ▾ → Reload plugins.

Files starting with "_" are ignored, so this template itself does nothing.
"""

NAME = 'My tools'          # group name shown in the Plugins menu


def hello(ctx):
    """ctx gives you:

    ctx.side       'local' or 'remote' – the pane the action was started from
    ctx.cwd        current folder of that pane
    ctx.paths      list of selected paths (full paths)
    ctx.input      the answer to your `ask` question (or None)
    ctx.sftp       paramiko SFTPClient for the server (None when not connected)
    ctx.site       the connected site's settings (dict) or None
    ctx.exec(cmd)  run a shell command on the server → (exit_code, stdout, stderr)
    ctx.upload(local_paths, remote_dir)    upload files/folders
    ctx.download(remote_paths, local_dir)  download files/folders
    ctx.log(msg)   write to the Log tab
    ctx.progress(done, total, current)     update the progress bar
    ctx.check_cancelled()                  call this in loops so Cancel works

    Return a string to show it in a window, or None to show nothing.
    Raise an exception to show an error.
    """
    return f'Hello! You selected {len(ctx.paths)} item(s) in {ctx.cwd} ({ctx.side}).'


ACTIONS = [
    {
        'id': 'hello',                    # unique within this file
        'label': 'Say hello',             # text in the menus
        'side': 'any',                    # 'local', 'remote' or 'any'
        'run': hello,
        # optional:
        # 'needs_selection': True,        # only enabled when something is selected
        # 'ask': 'Question to ask first', # shows an input box; answer is ctx.input
        # 'default': 'default answer',
        # 'confirm': 'Are you sure?',     # asks for confirmation first
    },
]
