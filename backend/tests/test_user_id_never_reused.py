"""A deleted account's id is never given to the next account, on either backend."""
from models import db, User


def test_the_last_account_deleted_leaves_its_id_unused(app, auth_client, create_user):
    made = []
    try:
        first = create_user(username='id_never_reused_first', role='viewer')
        last = create_user(username='id_never_reused_last', role='viewer')
        made += [first['id'], last['id']]
        assert auth_client.delete(f"/api/v2/users/{last['id']}").status_code == 200
        with app.app_context():
            assert db.session.query(db.func.max(User.id)).scalar() < last['id']
        following = create_user(username='id_never_reused_following', role='viewer')
        made.append(following['id'])
        assert following['id'] > last['id']
    finally:
        with app.app_context():
            for user_id in made:
                user = db.session.get(User, user_id)
                if user is not None:
                    db.session.delete(user)
            db.session.commit()
