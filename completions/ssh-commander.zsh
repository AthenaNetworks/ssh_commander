#compdef ssh-commander

_ssh_commander() {
    local curcontext="$curcontext" ret=1
    local -a state line
    local -A opt_args

    _arguments -C \
        '--config[Path to config file]:file:_files' \
        '--no-color[Disable colored output]' \
        '(-q --quiet)'{-q,--quiet}'[Suppress informational output]' \
        '(-v --verbose)'{-v,--verbose}'[Enable verbose output]' \
        '--timeout[SSH connect timeout in seconds]:seconds' \
        '--strict-host-key-checking[Reject unknown SSH host keys]' \
        '--version[Show version]' \
        '1: :->command' \
        '*::: :->args' && ret=0

    # Resolve the config file (mirrors what ssh-commander does)
    local config_file="$HOME/.config/ssh-commander/servers.yaml"
    if [[ -n ${opt_args[--config]} ]]; then
        config_file="${opt_args[--config]}"
    fi

    local -a tags hosts
    if [[ -f $config_file ]]; then
        tags=(${(f)"$(grep -oE 'tags:[^#]*' "$config_file" | sed -E 's/tags:[[:space:]]*\[?//; s/\].*$//; s/,/\n/g' | sed 's/^ *//;s/ *$//;s/^["'\'']//;s/["'\'']$//' | sort -u)"})
        hosts=(${(f)"$(grep -E '^- *hostname:' "$config_file" | sed -E 's/^- *hostname: *//; s/^[\"'\'' ]*//; s/[\"'\'' ]*$//' | sort -u)"})
    fi

    case $state in
        command)
            local -a commands
            commands=(
                'exec:Execute commands on servers'
                'add:Add a new server'
                'edit:Edit an existing server'
                'remove:Remove one or more servers'
                'list:List configured servers'
                'sync:Sync config from URL'
                'test:Test SSH connectivity to servers'
                'config-path:Print resolved config file path'
                'version:Print version'
            )
            _describe -t commands 'ssh-commander commands' commands && ret=0
            ;;
        args)
            case $words[1] in
                exec)
                    _arguments -C \
                        '(-c --command -f --file)'{-c,--command}'[Command to execute]:command' \
                        '(-f --file -c --command)'{-f,--file}'[File of commands]:filename:_files' \
                        '(-t --tags)'{-t,--tags}'[Filter servers by tags]:tag:($tags)' \
                        '(-p --parallel)'{-p,--parallel}'[Run on N servers in parallel]:N' \
                        '--stop-on-error[Stop on first command failure (with -f)]' && ret=0
                    ;;
                add)
                    _arguments -C \
                        '--hostname[Server hostname]:hostname' \
                        '--username[Username]:username' \
                        '--key-file[SSH key file]:file:_files' \
                        '--password[Password (insecure)]:password' \
                        '--password-stdin[Read password from stdin]' \
                        '--port[SSH port]:port' \
                        '--tags[Comma-separated tags]:tags' \
                        '(-y --yes)'{-y,--yes}'[Non-interactive]' && ret=0
                    ;;
                edit)
                    _arguments -C \
                        '1:hostname:($hosts)' \
                        '--rename[New hostname]:hostname' \
                        '--username[Username]:username' \
                        '--key-file[SSH key file]:file:_files' \
                        '--password[Password]:password' \
                        '--password-stdin[Read password from stdin]' \
                        '--port[SSH port]:port' \
                        '--tags[Comma-separated tags]:tags:($tags)' \
                        '--clear-password[Clear stored password]' \
                        '--clear-key-file[Clear stored key file]' && ret=0
                    ;;
                remove)
                    _arguments -C \
                        '*:hostname:($hosts)' \
                        '(-y --yes)'{-y,--yes}'[Skip confirmation]' && ret=0
                    ;;
                list)
                    _arguments -C \
                        '(-t --tag --tags)'{-t,--tag,--tags}'[Filter by tags]:tag:($tags)' \
                        '(-o --output)'{-o,--output}'[Output format]:format:(pretty hosts yaml json)' && ret=0
                    ;;
                test)
                    _arguments -C \
                        '(-t --tags)'{-t,--tags}'[Filter by tags]:tag:($tags)' \
                        '(-p --parallel)'{-p,--parallel}'[Parallel workers]:N' && ret=0
                    ;;
                sync)
                    _arguments -C \
                        '--dry-run[Preview without changes]' \
                        '--verify[Validate after download]' \
                        '--username[Username for SFTP]:username' \
                        '--key-file[SSH key file]:file:_files' \
                        '--branch[Git branch]:branch' \
                        '--keep-backups[Number of backups to keep]:N' \
                        '*:url:_urls' && ret=0
                    ;;
                config-path|version)
                    ret=0
                    ;;
            esac
            ;;
    esac

    return ret
}

_ssh_commander "$@"
