# Proves the runner works: answers with what Fusion reports, and changes nothing.
import adsk.core


def main(args):
    app = adsk.core.Application.get()
    return {'version': app.version, 'user': app.currentUser.displayName if app.currentUser else None,
            'project': app.data.activeProject.name if app.data.activeProject else None}
