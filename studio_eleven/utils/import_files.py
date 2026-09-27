import os

##########################################
# Import Files Function
##########################################

def get_import_filepaths(operator):
    """Files selected in the file browser, the filepath alone when the operator is called from a script."""
    filepaths = []

    for file in operator.files:
        if file.name:
            filepaths.append(os.path.join(operator.directory, file.name))

    if len(filepaths) == 0:
        filepaths.append(operator.filepath)

    return filepaths
