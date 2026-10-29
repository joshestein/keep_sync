# Master token stored via the `security` CLI, not `keyring`

`keyring` writes Keychain items whose ACL trusts the Python interpreter that created them. When uv changes the venv's interpreter path, the launchd agent hits an invisible Keychain prompt and stalls. Storing and reading through `/usr/bin/security` (`add-generic-password -T /usr/bin/security`, `find-generic-password -w`) pins the ACL to a path that never changes. The email is the item's account attribute, so no config file exists.
