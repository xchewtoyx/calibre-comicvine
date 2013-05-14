# Comicvine
A calibre metadata source plugin for comicvine.com

## Install

Dependencies:

 * pycomicvine (https://github.com/authmillenon/pycomicvine)
 * Levenshtein (optional)

For convenience, pycomicvine 0.9 is included in the distribution.
This will only be loaded if the module is not found elsewhere in the
system path

Create a plugin zip file containing the files listed in MANIFEST and
install.

On a Unix system this can be done using:

    $ zip Comicvine -@ < MANIFEST
    $ calibre-customize -a Comicvine.zip

The single command `calibre-customize -b .` from within the source
directory will also work, but will include many unnecessary files.

## Usage 

Allows you to search comicvine for metadata for your comics and
graphic novels stored in Calibre.

You will need an API Key to use this source
 
Get one at (http://www.comicvine.com/api/)

Once configured you can use this plugin from the GUI (download
metadata) or from the fetch-ebook-metadata command.  

Both of these methods will try all active metadata sources, and only
return the most preferred result.

To return all comicvine matches from the command line you can search
using:

    $ calibre-debug -r Comicvine [t:title] [a:author] [i:type:id]

This will search for comics that match the given fields.  Any spaces
should be enclosed in quotes, e.g.: 

    $ calibre-debug -r Comicvine t:'The Invisibles #15' \
        a:'Grant Morrison'
    Found: The Invisibles #15: She-Man, Part Three: Apocalipstick [1995-12-01 00:00:00]
    Found: The Invisibles, Volume Two #15: The Philadelphia Experiment [1998-05-01 00:00:00]

or:

    $ calibre-debug -r Comicvine i:comicvine:41736
    Found: The Invisibles #15: She-Man, Part Three: Apocalipstick [1995-12-01 00:00:00]

## Contribute 

You can contribute by submitting issue tickets on GitHub
(https://github.com/authmillenon/pycomicvine), including Pull
Requests. You can test the comicvine plugin by calling:

    calibre-debug -e __init__.py

## License
Copyright (c) 2013 Russell Heilling

pycomicvine is Copyright (c) Martin Lenders
