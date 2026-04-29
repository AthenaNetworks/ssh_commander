# bash completion for ssh-commander

_ssh_commander() {
    local cur prev words cword
    _init_completion || return

    # List of all commands
    local commands="exec add edit remove list sync test config-path version"
    local global_opts="--config --no-color -q --quiet -v --verbose --timeout --strict-host-key-checking --version -h --help"

    # Find the subcommand (skip global options that take values)
    local i=1 cmd=""
    while [[ $i -lt $cword ]]; do
        case "${words[i]}" in
            --config|--timeout)
                i=$((i + 2))
                ;;
            -*)
                i=$((i + 1))
                ;;
            *)
                cmd="${words[i]}"
                break
                ;;
        esac
    done

    # Top-level command completion
    if [[ -z $cmd ]]; then
        if [[ $cur == -* ]]; then
            COMPREPLY=( $(compgen -W "$global_opts" -- "$cur") )
        else
            COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        fi
        return 0
    fi

    # Resolve the config file the same way ssh-commander does.
    local config_file
    if [[ -f "$HOME/.config/ssh-commander/servers.yaml" ]]; then
        config_file="$HOME/.config/ssh-commander/servers.yaml"
    fi
    # Honour --config FILE if present in the words array
    local j=1
    while [[ $j -lt ${#words[@]} ]]; do
        if [[ "${words[j]}" == "--config" && $((j + 1)) -lt ${#words[@]} ]]; then
            config_file="${words[$((j + 1))]}"
            break
        fi
        j=$((j + 1))
    done

    local hosts="" tags=""
    if [[ -n $config_file && -f $config_file ]]; then
        hosts=$(grep -E '^- *hostname:' "$config_file" | sed -E 's/^- *hostname: *//; s/^[\"'\'' ]*//; s/[\"'\'' ]*$//' | sort -u)
        tags=$(grep -oE 'tags:[^#]*' "$config_file" | sed -E 's/tags:[[:space:]]*\[?//; s/\].*$//; s/,/\n/g' | sed 's/^ *//;s/ *$//;s/^["'\'']//;s/["'\'']$//' | sort -u)
    fi

    case $cmd in
        exec)
            case $prev in
                -c|--command)
                    return 0
                    ;;
                -f|--file)
                    _filedir
                    return 0
                    ;;
                -t|--tags)
                    COMPREPLY=( $(compgen -W "$tags" -- "$cur") )
                    return 0
                    ;;
                -p|--parallel)
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-c --command -f --file -t --tags -p --parallel --stop-on-error" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        add)
            case $prev in
                --hostname|--username|--password|--port|--tags)
                    return 0
                    ;;
                --key-file)
                    _filedir
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "--hostname --username --key-file --password --password-stdin --port --tags -y --yes" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        edit)
            if [[ $cword -le 2 ]] || [[ "${words[$((cword - 1))]}" == "edit" ]]; then
                COMPREPLY=( $(compgen -W "$hosts" -- "$cur") )
                return 0
            fi
            case $prev in
                --rename|--username|--password|--port|--tags)
                    return 0
                    ;;
                --key-file)
                    _filedir
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "--rename --username --key-file --password --password-stdin --port --tags --clear-password --clear-key-file" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        remove)
            COMPREPLY=( $(compgen -W "$hosts -y --yes" -- "$cur") )
            return 0
            ;;
        list)
            case $prev in
                -t|--tag|--tags)
                    COMPREPLY=( $(compgen -W "$tags" -- "$cur") )
                    return 0
                    ;;
                -o|--output)
                    COMPREPLY=( $(compgen -W "pretty hosts yaml json" -- "$cur") )
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-t --tag --tags -o --output" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        test)
            case $prev in
                -t|--tags)
                    COMPREPLY=( $(compgen -W "$tags" -- "$cur") )
                    return 0
                    ;;
                -p|--parallel)
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "-t --tags -p --parallel" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        sync)
            case $prev in
                --key-file)
                    _filedir
                    return 0
                    ;;
                --branch|--username|--keep-backups)
                    return 0
                    ;;
                *)
                    COMPREPLY=( $(compgen -W "--dry-run --verify --username --key-file --branch --keep-backups" -- "$cur") )
                    return 0
                    ;;
            esac
            ;;
        config-path|version)
            return 0
            ;;
    esac
}

complete -F _ssh_commander ssh-commander
