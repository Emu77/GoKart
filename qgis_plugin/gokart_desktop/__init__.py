def classFactory(iface):
    from .plugin import GoKartPlugin
    return GoKartPlugin(iface)
