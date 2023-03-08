import modules.db.sql as sql
import modules.roxywi.common as roxywi_common


def update_group(group_id: int, group_name: str, desc: str) -> None:
    print(group_name)
    if group_name == '':
        print(roxywi_common.return_error_message())
    else:
        try:
            sql.update_group(group_name, desc, group_id)
            roxywi_common.logging('Roxy-WI server', f'The {group_name} has been updated', roxywi=1, login=1)
        except Exception as e:
            print(f'error: {e}')


def delete_group(group_id: int) -> None:
    group = sql.select_groups(id=group_id)
    group_name = ''

    for g in group:
        group_name = g.name

    if sql.delete_group(group_id):
        print("Ok")
        roxywi_common.logging('Roxy-WI server', f'The {group_name} has been deleted', roxywi=1, login=1)
