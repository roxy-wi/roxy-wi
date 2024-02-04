import app.modules.db.sql as sql
import app.modules.roxywi.common as roxywi_common


def update_group(group_id: int, group_name: str, desc: str) -> str:
    if group_name == '':
        return roxywi_common.return_error_message()
    else:
        try:
            sql.update_group(group_name, desc, group_id)
            roxywi_common.logging('Roxy-WI server', f'The {group_name} has been updated', roxywi=1, login=1)
            return 'ok'
        except Exception as e:
            return f'error: {e}'


def delete_group(group_id: int) -> str:
    group = sql.select_groups(id=group_id)
    group_name = ''

    for g in group:
        group_name = g.name

    if sql.delete_group(group_id):
        roxywi_common.logging('Roxy-WI server', f'The {group_name} has been deleted', roxywi=1, login=1)
        return 'ok'
