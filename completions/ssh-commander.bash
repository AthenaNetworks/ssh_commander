# bash completion for ssh-commander

_ssh_commander() {
    local cur prev words cword
    _init_completion || return

    # List of all commands
    local commands="exec add remove list sync"

    # Handle command completion
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return 0
    fi

    # Handle subcommand arguments
    case ${words[1]} in
        exec)
            case $prev in
                -c|--command)
                    # Command completion - no suggestions
                    return 0
                    ;;
                -f|--file)
                    # File completion
                    _filedir
                    return 0
                    ;;
                --tags)
                    # Try to get tags from config file
                    local config_file="$HOME/.config/ssh-commander/servers.yaml"
                    if [[ -f $config_file ]]; then
                        local tags=$(grep -o 'tags:.*' "$config_file" | cut -d'[' -f2 | cut -d']' -f1 | tr ',' '\n' | sed 's/^ *//;s/ *$//' | sort -u)
                        COMPREPLY=( $(compgen -W "$tags" -- "$cur") )
                    fi
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-c --command -f --file --tags" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        remove)
            # Try to get hostnames from config file
            local config_file="$HOME/.config/ssh-commander/servers.yaml"
            if [[ -f $config_file ]]; then
                local hosts=$(grep 'hostname:' "$config_file" | cut -d':' -f2 | sed 's/^ *//' | sort -u)
                COMPREPLY=( $(compgen -W "$hosts" -- "$cur") )
            fi
            return 0
            ;;
        sync)
            case $prev in
                --key-file)
                    # SSH key file completion
                    _filedir
                    return 0
                    ;;
                --branch)
                    # No branch completion yet
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "--dry-run --verify --username --key-file --branch" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        list|add)
            # No additional arguments
            return 0
            ;;
    esac
}

complete -F _ssh_commander ssh-commander
