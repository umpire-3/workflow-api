from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from main import app, get_session
from models import Base


db_url = "sqlite://"
engine = create_engine(
    db_url,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def override_get_session():
    try:
        session = TestingSessionLocal()
        yield session
    finally:
        session.close()


app.dependency_overrides[get_session] = override_get_session

client = TestClient(app)


def test_workflow_created_successfully():
    create_url = app.url_path_for('create_workflow')
    response = client.post(create_url, json={'name': 'test-workflow'})

    assert response.status_code == 201
    data = response.json()
    assert data['id'] == 1
    assert data['name'] == 'test-workflow'


def test_list_workflows():
    list_url = app.url_path_for('list_workflows')
    response = client.get(list_url)

    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_workflow_successfully():
    get_url = app.url_path_for('get_workflow', workflow_id=1)
    response = client.get(get_url)

    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 1
    assert data['name'] == 'test-workflow'


def test_get_workflow_not_found():
    get_url = app.url_path_for('get_workflow', workflow_id=2)
    response = client.get(get_url)

    assert response.status_code == 404


def test_workflow_renamed_successfully():
    update_url = app.url_path_for('update_workflow', workflow_id=1)
    response = client.put(update_url, json={'name': 'renamed-test-workflow'})

    assert response.status_code == 200
    data = response.json()
    assert data['name'] == 'renamed-test-workflow'


def test_workflow_deleted_successfuly():
    delete_url = app.url_path_for('delete_workflow', workflow_id=1)
    response = client.delete(delete_url)

    assert response.status_code == 200
    assert response.json()['ok']


def test_startnode_created_successfully():
    create_url = app.url_path_for('create_workflow')
    client.post(create_url, json={'name': 'test-workflow'})

    create_url = app.url_path_for('create_start_node')
    response = client.post(create_url, json={'workflow_id': 1})

    assert response.status_code == 201
    data = response.json()
    assert data['workflow_id'] == 1


def test_endnode_created_successfully():
    create_url = app.url_path_for('create_end_node')
    response = client.post(create_url, json={'workflow_id': 1})

    assert response.status_code == 201
    data = response.json()
    assert data['workflow_id'] == 1


def test_messagenode_created_successfully():
    create_url = app.url_path_for('create_message_node')
    response = client.post(create_url, json={'workflow_id': 1, 'status': 'opened', 'text': 'Hello'})

    assert response.status_code == 201
    data = response.json()
    assert data['workflow_id'] == 1
    assert data['status'] == 'opened'
    assert data['text'] == 'Hello'


def test_messagenode_created_failed():
    create_url = app.url_path_for('create_message_node')
    response = client.post(create_url, json={'workflow_id': 1, 'status': 'invalid', 'text': 'Hello'})

    assert response.status_code == 422


def test_conditionnode_created_successfully():
    create_url = app.url_path_for('create_condition_node')
    response = client.post(create_url, json={'workflow_id': 1, 'condition': 'status = "opened"'})

    assert response.status_code == 201
    data = response.json()
    assert data['workflow_id'] == 1
    assert data['condition'] == 'status = "opened"'


def test_get_node_successfully():
    get_url = app.url_path_for('get_node', node_id=1)
    response = client.get(get_url)

    assert response.status_code == 200
    data = response.json()
    assert data['id'] == 1
    assert data['type'] == 'startnode'


def test_messagenode_update_successfully():
    update_url = app.url_path_for('update_message_node', node_id=3)
    response = client.put(update_url, json={'status': 'sent', 'text': 'Goodbye'})

    assert response.status_code == 200
    data = response.json()
    assert data['status'] == 'sent'
    assert data['text'] == 'Goodbye'


def test_conditionnode_update_successfully():
    update_url = app.url_path_for('update_condition_node', node_id=4)
    response = client.put(update_url, json={'condition': 'status = "sent"'})

    assert response.status_code == 200
    data = response.json()
    assert data['condition'] == 'status = "sent"'


def test_node_deleted_successfully():
    delete_url = app.url_path_for('delete_node', node_id=1)
    response = client.delete(delete_url)

    assert response.status_code == 200
    assert response.json()['ok']

    get_url = app.url_path_for('get_node', node_id=1)
    response = client.get(get_url)

    assert response.status_code == 404


def test_connect_nodes_from_different_workflows_failes():
    create_url = app.url_path_for('create_workflow')
    response = client.post(create_url, json={'name': 'test-workflow-1'})
    workflow_1_id = response.json()['id']
    
    response = client.post(create_url, json={'name': 'test-workflow-2'})
    workflow_2_id = response.json()['id']

    create_url = app.url_path_for('create_end_node')
    response = client.post(create_url, json={'workflow_id': workflow_1_id})
    end_node_id = response.json()['id']

    create_url = app.url_path_for('create_start_node')
    response = client.post(create_url, json={'workflow_id': workflow_2_id, 'successor_id': end_node_id})

    assert response.status_code == 422
    assert response.json()['detail'] == 'You cannot connect nodes from different workflows'


def test_workflow_launch_successfully():
    create_url = app.url_path_for('create_workflow')
    response = client.post(create_url, json={'name': 'successful-workflow'})
    workflow_id = response.json()['id']

    create_url = app.url_path_for('create_end_node')
    response = client.post(create_url, json={'workflow_id': workflow_id})
    end_node_id = response.json()['id']

    create_url = app.url_path_for('create_message_node')
    response = client.post(create_url, json={
        'workflow_id': workflow_id, 
        'status': 'pending', 
        'text': 'How are you?',
        'successor_id': end_node_id
    })
    how_are_you_node_id = response.json()['id']
    
    response = client.post(create_url, json={
        'workflow_id': workflow_id, 
        'status': 'pending', 
        'text': 'How old are you?',
        'successor_id': end_node_id
    })
    how_old_are_you_node_id = response.json()['id']
    
    response = client.post(create_url, json={
        'workflow_id': workflow_id, 
        'status': 'pending', 
        'text': 'Do you like pets?',
        'successor_id': end_node_id
    })
    do_you_like_pets_node_id = response.json()['id']
    
    create_url = app.url_path_for('create_condition_node')
    response = client.post(create_url, json={
        'workflow_id': workflow_id,
        'condition': 'status == "opened"',
        'yes_successor_id': how_old_are_you_node_id,
        'no_successor_id': do_you_like_pets_node_id
    })
    status_opened_node_id = response.json()['id']
    
    response = client.post(create_url, json={
        'workflow_id': workflow_id,
        'condition': 'status == "sent"',
        'yes_successor_id': how_are_you_node_id,
        'no_successor_id': status_opened_node_id
    })
    status_sent_node_id = response.json()['id']

    create_url = app.url_path_for('create_message_node')
    response = client.post(create_url, json={
        'workflow_id': workflow_id, 
        'status': 'opened', 
        'text': 'Hello',
        'successor_id': status_sent_node_id
    })
    hello_node_id = response.json()['id']

    create_url = app.url_path_for('create_start_node')
    response = client.post(create_url, json={'workflow_id': workflow_id, 'successor_id': hello_node_id})
    start_node_id = response.json()['id']

    launch_url = app.url_path_for('launch_workflow', workflow_id=workflow_id)
    response = client.get(launch_url)

    assert response.status_code == 200
    data = response.json()
    assert [node['id'] for node in data['path']] == [
        start_node_id,
        hello_node_id,
        status_sent_node_id,
        status_opened_node_id,
        how_old_are_you_node_id,
        end_node_id
    ]


def test_workflow_launch_no_startnode():
    create_url = app.url_path_for('create_workflow')
    response = client.post(create_url, json={'name': 'no-startnode-workflow'})
    workflow_id = response.json()['id']

    create_url = app.url_path_for('create_end_node')
    response = client.post(create_url, json={'workflow_id': workflow_id})
    end_node_id = response.json()['id']

    create_url = app.url_path_for('create_message_node')
    response = client.post(create_url, json={
        'workflow_id': workflow_id, 
        'status': 'pending', 
        'text': 'How are you?',
        'successor_id': end_node_id
    })

    launch_url = app.url_path_for('launch_workflow', workflow_id=workflow_id)
    response = client.get(launch_url)

    assert response.status_code == 400
    assert response.json()['detail'] == 'No start node'


def test_workflow_launch_no_endnode():
    create_url = app.url_path_for('create_workflow')
    response = client.post(create_url, json={'name': 'no-endnode-workflow'})
    workflow_id = response.json()['id']

    create_url = app.url_path_for('create_message_node')
    response = client.post(create_url, json={
        'workflow_id': workflow_id, 
        'status': 'pending', 
        'text': 'How are you?'
    })
    message_node_id = response.json()['id']

    create_url = app.url_path_for('create_start_node')
    response = client.post(create_url, json={'workflow_id': workflow_id, 'successor_id': message_node_id})

    launch_url = app.url_path_for('launch_workflow', workflow_id=workflow_id)
    response = client.get(launch_url)

    assert response.status_code == 400
    assert response.json()['detail'] == f'Message node(id: {message_node_id}) should have exactly one successor node'


def test_workflow_launch_conditionnode_without_messagenode():
    create_url = app.url_path_for('create_workflow')
    response = client.post(create_url, json={'name': 'conditionnode-without-messagenode-workflow'})
    workflow_id = response.json()['id']

    create_url = app.url_path_for('create_end_node')
    response = client.post(create_url, json={'workflow_id': workflow_id})
    end_node_id = response.json()['id']
    
    create_url = app.url_path_for('create_condition_node')
    response = client.post(create_url, json={
        'workflow_id': workflow_id,
        'condition': 'status == "opened"',
        'yes_successor_id': end_node_id,
        'no_successor_id': end_node_id
    })
    condition_node_id = response.json()['id']

    create_url = app.url_path_for('create_start_node')
    response = client.post(create_url, json={'workflow_id': workflow_id, 'successor_id': condition_node_id})

    launch_url = app.url_path_for('launch_workflow', workflow_id=workflow_id)
    response = client.get(launch_url)

    assert response.status_code == 400
    assert response.json()['detail'] == f'Condition node(id: {condition_node_id}) should have message node or another condition node as its predecessor'
