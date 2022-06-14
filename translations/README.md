
# Translations workflow

1. Add new strings in the code which need to be translated as _('my string')
2. After adding new strings to the code which need to be translated, run extract.sh on your host (you might need to pip install babel on your host). You could also do within the container and then extract the en.pot file to your host. 
3. Commit the updated en.pot file; submitting a PR on github with a change to en.pot will trigger a translation workflow on LingoHub
4. LingoHub will open a PR to update ar.po with the updated translations


 
