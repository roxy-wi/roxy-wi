# Executed under a host-wide flock by haproxy_files.candidate_command.
set -eu
export LC_ALL=C
target=$1 candidate=$2 action=$3 container=$4 reload_command=$5 root=$6 main=$7 token=$8
shift 8
work=$(mktemp -d)
next=''
# The managed Docker role mounts /tmp read-only. Stage outside that mount.
container_candidate="/roxywi-$token.cfg"
copied=0
applied=0
completed=0
keep_backup=0
cleanup() {
    rc=$?
    trap - EXIT HUP INT TERM
    if [ "$applied" = 1 ] && [ "$completed" = 0 ]; then
        if [ -f "$work/before" ]; then
            restore=''
            if restore=$(mktemp "$(dirname -- "$resolved")/.roxywi-restore.XXXXXX") &&
               cp --preserve=all -- "$work/before" "$restore" && mv -f -- "$restore" "$resolved"; then
                echo 'The previous configuration file was restored' >&2
            else
                keep_backup=1
                printf 'Could not restore the previous configuration file; backup retained at %s\n' "$work/before" >&2
                if [ -n "$restore" ]; then rm -f -- "$restore" || rc=1; fi
            fi
        else
            rm -f -- "$resolved" || echo 'Could not remove the newly created configuration file' >&2
        fi
        rc=1
    fi
    if [ "$copied" = 1 ]; then
        if ! docker exec -u 0 "$container" rm -f "$container_candidate"; then rc=1; fi
    fi
    if [ -n "$next" ]; then rm -f -- "$next" || rc=1; fi
    if [ -n "$candidate" ]; then rm -f -- "$candidate" || rc=1; fi
    if [ "$keep_backup" = 0 ]; then rm -rf -- "$work" || rc=1; fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
root=$(realpath -m -- "$root")
resolved=$(realpath -m -- "$target")
main=$(realpath -m -- "$main")
case "$resolved" in
    "$main"|"$root"/*.cfg) ;;
    *) echo 'Selected configuration resolves outside the HAProxy directory' >&2; exit 1 ;;
esac
if [ -n "$container" ]; then
    docker inspect --format '{{range .Mounts}}{{println .Source}}{{println .Destination}}{{println .RW}}{{end}}' "$container" > "$work/mounts"
fi
container_path() {
    mapped_path=''
    mapped_length=0
    mapped_writable=false
    mapped_directory=false
    while IFS= read -r mount_source && IFS= read -r mount_target && IFS= read -r writable; do
        mount_source=$(realpath -m -- "$mount_source")
        case "$1" in
            "$mount_source") relative='' ;;
            "$mount_source"/*) relative=${1#"$mount_source"} ;;
            *) continue ;;
        esac
        # Equal host paths can be mounted at several container destinations.
        # Prefer the writable alias regardless of Docker's mount ordering.
        if [ "${#mount_source}" -gt "$mapped_length" ] ||
           { [ "${#mount_source}" -eq "$mapped_length" ] && [ "$mapped_writable" != true ] && [ "$writable" = true ]; }; then
            mapped_path="${mount_target%/}$relative"
            mapped_length=${#mount_source}
            mapped_writable=$writable
            mapped_directory=false
            if [ -d "$mount_source" ]; then mapped_directory=true; fi
        fi
    done < "$work/mounts"
    if [ -z "$mapped_path" ]; then
        echo 'A configured HAProxy file is not mounted in the container' >&2
        return 1
    fi
    if [ "$2" = write ] && { [ "$mapped_writable" != true ] || [ "$mapped_directory" != true ]; }; then
        echo 'Mount the HAProxy configuration directory read-write before saving; single-file mounts cannot follow atomic replacements' >&2
        return 1
    fi
    printf '%s' "$mapped_path"
}
if [ -n "$container" ] && [ "$action" != test ] && [ "$action" != check ]; then
    container_path "$resolved" write > /dev/null
fi
# The candidate remains separate from the working configuration during validation.
if [ "$action" != check ]; then
    cp -- "$candidate" "$work/candidate.cfg"
    chmod 600 "$work/candidate.cfg"
fi
: > "$work/files"
for source in "$@"; do
    if [ -d "$source" ]; then
        : > "$work/source"
        for file in "$source"/*.cfg; do
            [ -f "$file" ] || continue
            printf '%s\n' "$file" >> "$work/source"
        done
        # A new file participates at its normal lexical position.
        if [ "$action" != check ] && [ "$(realpath -m -- "$(dirname -- "$target")")" = "$(realpath -e -- "$source")" ]; then
            case "$(basename -- "$target")" in .*) ;; *) printf '%s\n' "$target" >> "$work/source" ;; esac
        fi
        sort -u "$work/source" >> "$work/files"
    else
        printf '%s\n' "$source" >> "$work/files"
    fi
done
set --
selected=0
: > "$work/seen"
while IFS= read -r file; do
    canonical=$(realpath -m -- "$file")
    if grep -Fxq -- "$canonical" "$work/seen"; then
        echo 'Overlapping HAProxy -f sources load the same file more than once' >&2
        exit 1
    fi
    printf '%s\n' "$canonical" >> "$work/seen"
    if [ "$action" != check ] && [ "$canonical" = "$resolved" ]; then
        selected=$((selected + 1))
        if [ -n "$container" ]; then file=$container_candidate; else file="$work/candidate.cfg"; fi
    elif [ -n "$container" ]; then
        file=$(container_path "$canonical" read)
    fi
    set -- "$@" -f "$file"
done < "$work/files"
if [ "$action" != check ] && [ "$selected" != 1 ]; then
    echo 'Selected file is not included in HAProxy startup sources. Check the multiple configuration files option in the HAProxy service settings and configure startup with -f.' >&2
    exit 1
fi
if [ -n "$container" ]; then
    if [ "$action" != check ]; then
        docker cp "$work/candidate.cfg" "$container:$container_candidate"
        copied=1
        container_uid=$(docker exec "$container" id -u)
        container_gid=$(docker exec "$container" id -g)
        docker exec -u 0 "$container" chown "$container_uid:$container_gid" "$container_candidate"
    fi
    docker exec "$container" haproxy -c "$@"
else
    haproxy -c "$@"
fi
case "$action" in test|check) exit 0 ;; esac
# Preserve ownership, permissions and extended attributes of an existing file.
next=$(mktemp "$(dirname -- "$resolved")/.roxywi-config.XXXXXX")
if [ -f "$resolved" ]; then
    cp --preserve=all -- "$resolved" "$work/before"
    cp --preserve=all -- "$resolved" "$next"
else
    chmod 644 "$next"
fi
cat "$work/candidate.cfg" > "$next"
applied=1
mv -f -- "$next" "$resolved"
next=''
if [ -n "$reload_command" ] && ! sh -c "$reload_command"; then
    echo 'HAProxy action failed' >&2
    exit 1
fi
completed=1
