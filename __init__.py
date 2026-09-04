def classFactory(iface):
    from .layer_file_list import LayerFileListPlugin

    return LayerFileListPlugin(iface)
