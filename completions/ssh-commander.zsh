#compdef ssh-commander

_ssh_commander() {
    local curcontext="$curcontext" ret=1
    local -a state line
    local -A opt_args

    _arguments -C \
        '1: :->command' \
        '*: :->args' && ret=0

    # Get available tags from config file
    local -a tags
    local config_file="$HOME/.config/ssh-commander/servers.yaml"
    if [[ -f $config_file ]]; then
        tags=(${(f)"$(grep -o 'tags:.*' "$config_file" | cut -d'[' -f2 | cut -d']' -f1 | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sort -u)"})
    fi

    # Get available hostnames from config file
    local -a hosts
    if [[ -f $config_file ]]; then
        hosts=(${(f)"$(grep 'hostname:' "$config_file" | cut -d':' -f2 | sed 's/^ *//' | sort -u)"})
    fi

    case $state in
        command)
            local -a commands
            commands=(
                'exec:Execute commands on servers'
                'add:Add a new server'
                'remove:Remove a server'
                'list:List configured servers'
                'sync:Sync config from URL'
            )
            _describe -t commands 'ssh-commander commands' commands && ret=0
            ;;
        args)
            case $words[2] in
                exec)
                    _arguments -C \
                        '-c[Command to execute]:command' \
                        '--command[Command to execute]:command' \
                        '-f[Execute commands from file]:filename:_files' \
                        '--file[Execute commands from file]:filename:_files' \
                        '--tags[Filter servers by tags]:tag:($tags)' && ret=0
                    ;;
                remove)
                    _arguments -C \
                        '*:hostname:($hosts)' && ret=0
                    ;;
                sync)
                    _arguments -C \
                        '--dry-run[Show what would happen]' \
                        '--verify[Verify config format]' \
                        '--username[Username for SFTP]:username' \
                        '--key-file[SSH key file]:key file:_files' \
                        '--branch[Git branch]:branch' \
                        '*:url:_urls' && ret=0
                    ;;
                add|list)
                    # No additional arguments
                    ret=0
                    ;;
            esac
            ;;
    esac

    return ret
}

_ssh_commander "$@"
