# bash completion for transformers_ocr

_transformers_ocr() {
    local cur prev words cword
    _init_completion || return

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "recognize ocr hold start listen stop status restart download purge nuke -h --help" -- "$cur") )
        return
    fi

    case "${words[1]}" in
        recognize|ocr|hold)
            COMPREPLY=( $(compgen -W "--image-path" -- "$cur") )
            ;;
        start|listen)
            COMPREPLY=( $(compgen -W "--foreground" -- "$cur") )
            ;;
    esac
}

complete -F _transformers_ocr transformers_ocr
