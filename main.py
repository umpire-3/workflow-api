import networkx as nx
import rule_engine
from typing import Type
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session, selectin_polymorphic

from models import (
    model_to_dict,
    Base, 
    Workflow, 
    Edge,
    Node, 
    StartNode, 
    EndNode, 
    MessageNode, 
    ConditionNode
)
from schemas import (
    WorkflowRead, 
    WorkflowCreate, 
    WorkflowUpdate,
    StartNodeCreate,
    StartNodeUpdate,
    EndNodeCreate,
    EndNodeUpdate,
    MessageNodeCreate,
    MessageNodeUpdate, 
    ConditionNodeCreate,
    ConditionNodeUpdate
)


sqlite_file_name = 'database.db'
sqlite_url = f'sqlite:///{sqlite_file_name}'

connect_args = {'check_same_thread': False}
engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)

Base.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def exclude_keys(dictionary, keys):
    return {key: value for key, value in dictionary.items() if key not in keys}


app = FastAPI()


@app.get('/workflows', name='list_workflows')
def list_workflows(db: Session = Depends(get_session)):
    query = select(Workflow)
    return db.scalars(query).all()


@app.post('/workflows', name='create_workflow', response_model=WorkflowRead, status_code=201)
def create_workflow(workflow: WorkflowCreate, db: Session = Depends(get_session)):
    db_workflow = Workflow(**workflow.model_dump())
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return db_workflow


def get_workflow_or_404(workflow_id: int, db: Session) -> Workflow:
    query = select(Workflow).where(Workflow.id == workflow_id)
    result = db.scalars(query).first()
    
    if result is None:
        raise HTTPException(status_code=404, detail='Workflow not found')
    
    return result


@app.get('/workflows/{workflow_id}', name='get_workflow', response_model=WorkflowRead)
def get_workflow(workflow_id: int, db: Session = Depends(get_session)):
    return get_workflow_or_404(workflow_id, db)


@app.put('/workflows/{workflow_id}', name='update_workflow', response_model=WorkflowRead)
def update_workflow(workflow_id: int, workflow: WorkflowUpdate, db: Session = Depends(get_session)):
    db_workflow = get_workflow_or_404(workflow_id, db)
    workflow_data = workflow.model_dump(exclude_unset=True)
    
    for attr, value in workflow_data.items():
        setattr(db_workflow, attr, value)
    
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return db_workflow


@app.delete('/workflows/{workflow_id}', name='delete_workflow')
def delete_workflow(workflow_id: int, db: Session = Depends(get_session)):
    workflow = get_workflow_or_404(workflow_id, db)
    db.delete(workflow)
    db.commit()
    return {'ok': True}


@app.get('/workflows/{workflow_id}/nodes', name='list_workflow_nodes')
def list_workflow_nodes(workflow_id: int, db: Session = Depends(get_session)):
    # Check if given workflow exists
    get_workflow_or_404(workflow_id, db)

    loader_opt = selectin_polymorphic(Node, [StartNode, EndNode, MessageNode, ConditionNode])
    query = select(Node).where(Node.workflow_id == workflow_id).options(loader_opt)
    return db.scalars(query).all()


@app.get('/nodes', name='list_nodes')
def list_nodes(db: Session = Depends(get_session)):
    loader_opt = selectin_polymorphic(Node, [StartNode, EndNode, MessageNode, ConditionNode])
    query = select(Node).options(loader_opt)
    return db.scalars(query).all()


def validate_edge(out_node: int | Node, in_node: int | Node, db: Session):
    if isinstance(out_node, int):
        out_id = out_node
        out_node = db.get(Node, out_node)
    if isinstance(in_node, int):
        in_id = in_node
        in_node = db.get(Node, in_node)

    if out_node is None:
        raise HTTPException(status_code=422, detail=f'Node with id = {out_id} doesn\'t exist and cannot be used as predecessor for current node')
    if in_node is None:
        raise HTTPException(status_code=422, detail=f'Node with id = {in_id} doesn\'t exist and cannot be used as successor for current node')

    if out_node.id == in_node.id:
        raise HTTPException(status_code=422, detail='Self connected nodes are not allowed')
    
    if out_node.workflow_id != in_node.workflow_id:
        raise HTTPException(status_code=422, detail='You cannot connect nodes from different workflows')


@app.post('/nodes/startnode', name='create_start_node', status_code=201)
def create_start_node(node: StartNodeCreate, db: Session = Depends(get_session)):
    # Check if given workflow exists
    get_workflow_or_404(node.workflow_id, db)

    query = select(StartNode).where(StartNode.workflow_id == node.workflow_id)
    if len(db.scalars(query).all()) > 0:
        raise HTTPException(status_code=400, detail='Start node already exist for the current workflow')
    
    db_node = StartNode(workflow_id=node.workflow_id)
    db.add(db_node)
    db.flush()
    db.refresh(db_node)

    if node.successor_id:
        validate_edge(db_node, node.successor_id, db)
        edge = Edge(out_id=db_node.id, in_id=node.successor_id)
        db.add(edge)

    db.commit()
    db.refresh(db_node)

    return db_node


@app.post('/nodes/endnode', name='create_end_node', status_code=201)
def create_end_node(node: EndNodeCreate, db: Session = Depends(get_session)):
    # Check if given workflow exists
    get_workflow_or_404(node.workflow_id, db)
    
    query = select(EndNode).where(EndNode.workflow_id == node.workflow_id)
    if len(db.scalars(query).all()) > 0:
        raise HTTPException(status_code=400, detail='End node already exist for the current workflow')
    
    db_node = EndNode(workflow_id=node.workflow_id)
    db.add(db_node)
    db.flush()
    db.refresh(db_node)
    
    if node.predecessors:
        for predecessor_id in node.predecessors:
            validate_edge(predecessor_id, db_node, db)
            edge = Edge(out_id=predecessor_id, in_id=db_node.id)
            db.add(edge)
        
    db.commit()
    db.refresh(db_node)
    
    return db_node


@app.post('/nodes/messagenode', name='create_message_node', status_code=201)
def create_message_node(node: MessageNodeCreate, db: Session = Depends(get_session)):
    # Check if given workflow exists
    get_workflow_or_404(node.workflow_id, db)

    db_node = MessageNode(**exclude_keys(node.model_dump(), ('predecessors', 'successor_id')))
    db.add(db_node)
    db.flush()
    db.refresh(db_node)

    if node.predecessors:
        for predecessor_id in node.predecessors:
            validate_edge(predecessor_id, db_node, db)
            edge = Edge(out_id=predecessor_id, in_id=db_node.id)
            db.add(edge)
    
    if node.successor_id:
        validate_edge(db_node, node.successor_id, db)
        edge = Edge(out_id=db_node.id, in_id=node.successor_id)
        db.add(edge)

    db.commit()
    db.refresh(db_node)
    
    return db_node


@app.post('/nodes/conditionnode', name='create_condition_node', status_code=201)
def create_condition_node(node: ConditionNodeCreate, db: Session = Depends(get_session)):
    # Check if given workflow exists
    get_workflow_or_404(node.workflow_id, db)

    db_node = ConditionNode(**exclude_keys(node.model_dump(), ('predecessors', 'yes_successor_id', 'no_successor_id')))
    db.add(db_node)
    db.flush()
    db.refresh(db_node)

    if node.predecessors:
        for predecessor_id in node.predecessors:
            validate_edge(predecessor_id, db_node, db)
            edge = Edge(out_id=predecessor_id, in_id=db_node.id)
            db.add(edge)
    
    if node.yes_successor_id:
        validate_edge(db_node, node.yes_successor_id, db)
        edge = Edge(out_id=db_node.id, in_id=node.yes_successor_id, label='Yes')
        db.add(edge)
    
    if node.no_successor_id:
        validate_edge(db_node, node.no_successor_id, db)
        edge = Edge(out_id=db_node.id, in_id=node.no_successor_id, label='No')
        db.add(edge)
        
    db.commit()
    db.refresh(db_node)
    
    return db_node


def get_node_or_404(node_cls: Type[Node], node_id: int, db: Session) -> Node:
    loader_opt = selectin_polymorphic(Node, [StartNode, EndNode, MessageNode, ConditionNode])
    query = select(node_cls).where(node_cls.id == node_id).options(loader_opt)
    result = db.scalars(query).first()

    if result is None:
        raise HTTPException(status_code=404, detail='Node not found')
    
    return result


@app.get('/nodes/{node_id}', name='get_node')
def get_node(node_id: int, db: Session = Depends(get_session)):
    return get_node_or_404(Node, node_id, db)


@app.delete('/nodes/{node_id}', name='delete_node')
def delete_node(node_id: int, db: Session = Depends(get_session)):
    node = get_node_or_404(Node, node_id, db)
    db.delete(node)
    db.commit()
    return {'ok': True}


def delete_all_edges(node_id: int, db: Session):
    query = select(Edge).where(or_(Edge.in_id == node_id, Edge.out_id == node_id))

    for edge in db.scalars(query):
        db.delete(edge)


@app.put('/nodes/startnode/{node_id}', name='update_start_node')
def update_start_node(node_id: int, node: StartNodeUpdate, db: Session = Depends(get_session)):
    db_node = get_node_or_404(StartNode, node_id, db)
    node_data = exclude_keys(node.model_dump(exclude_unset=True), ('successor_id',))
    if 'workflow_id' in node_data:
        # Check if given workflow exists
        get_workflow_or_404(node.workflow_id, db)
        if node.workflow_id != db_node.workflow_id:
            # If we move node to another workflow we need to clear its connections with nodes from old workflow
            delete_all_edges(node_id, db)

    for attr, value in node_data.items():
        setattr(db_node, attr, value)
    
    db.add(db_node)
    
    if node.successor_id:
        validate_edge(db_node, node.successor_id, db)

        query = select(Edge).where(Edge.out_id == db_node.id)
        edge = db.scalars(query).first()
        if edge:
            edge.in_id = node.successor_id
        else:
            edge = Edge(out_id=db_node.id, in_id=node.successor_id)
        
        db.add(edge)
    
    db.commit()
    db.refresh(db_node)
    
    return db_node


@app.put('/nodes/endnode/{node_id}', name='update_end_node')
def update_end_node(node_id: int, node: EndNodeUpdate, db: Session = Depends(get_session)):
    db_node = get_node_or_404(EndNode, node_id, db)
    node_data = exclude_keys(node.model_dump(exclude_unset=True), ('predecessors',))
    if 'workflow_id' in node_data:
        # Check if given workflow exists
        get_workflow_or_404(node.workflow_id, db)
        if node.workflow_id != db_node.workflow_id:
            # If we move node to another workflow we need to clear its connections with nodes from old workflow
            delete_all_edges(node_id, db)

    for attr, value in node_data.items():
        setattr(db_node, attr, value)
    
    db.add(db_node)

    if node.predecessors:
        for predecessor_id in node.predecessors:
            validate_edge(predecessor_id, db_node, db)
            edge = Edge(out_id=predecessor_id, in_id=db_node.id)
            db.add(edge)
    
    db.commit()
    db.refresh(db_node)
    
    return db_node


@app.put('/nodes/messagenode/{node_id}', name='update_message_node')
def update_message_node(node_id: int, node: MessageNodeUpdate, db: Session = Depends(get_session)):
    db_node = get_node_or_404(MessageNode, node_id, db)
    node_data = exclude_keys(node.model_dump(exclude_unset=True), ('predecessors', 'successor_id'))
    if 'workflow_id' in node_data:
        # Check if given workflow exists
        get_workflow_or_404(node.workflow_id, db)
        if node.workflow_id != db_node.workflow_id:
            # If we move node to another workflow we need to clear its connections with nodes from old workflow
            delete_all_edges(node_id, db)

    for attr, value in node_data.items():
        setattr(db_node, attr, value)
    
    db.add(db_node)

    if node.predecessors:
        for predecessor_id in node.predecessors:
            validate_edge(predecessor_id, db_node, db)
            edge = Edge(out_id=predecessor_id, in_id=db_node.id)
            db.add(edge)
    
    if node.successor_id:
        validate_edge(db_node, node.successor_id, db)

        query = select(Edge).where(Edge.out_id == db_node.id)
        edge = db.scalars(query).first()
        if edge:
            edge.in_id = node.successor_id
        else:
            edge = Edge(out_id=db_node.id, in_id=node.successor_id)
        
        db.add(edge)

    db.commit()
    db.refresh(db_node)

    return db_node


@app.put('/nodes/conditionnode/{node_id}', name='update_condition_node')
def update_condition_node(node_id: int, node: ConditionNodeUpdate, db: Session = Depends(get_session)):
    db_node = get_node_or_404(ConditionNode, node_id, db)
    node_data = exclude_keys(node.model_dump(exclude_unset=True), ('predecessors', 'yes_successor_id', 'no_successor_id'))
    if 'workflow_id' in node_data:
        # Check if given workflow exists
        get_workflow_or_404(node.workflow_id, db)
        if node.workflow_id != db_node.workflow_id:
            # If we move node to another workflow we need to clear its connections with nodes from old workflow
            delete_all_edges(node_id, db)

    for attr, value in node_data.items():
        setattr(db_node, attr, value)
    
    db.add(db_node)

    if node.predecessors:
        for predecessor_id in node.predecessors:
            validate_edge(predecessor_id, db_node, db)
            edge = Edge(out_id=predecessor_id, in_id=db_node.id)
            db.add(edge)
    
    if node.yes_successor_id:
        validate_edge(db_node, node.yes_successor_id, db)
        
        query = select(Edge).where(Edge.out_id == db_node.id, Edge.label == 'Yes')
        edge = db.scalars(query).first()
        if edge:
            edge.in_id = node.yes_successor_id
        else:
            edge = Edge(out_id=db_node.id, in_id=node.yes_successor_id, label='Yes')
        
        db.add(edge)
    
    if node.no_successor_id:
        validate_edge(db_node, node.no_successor_id, db)

        query = select(Edge).where(Edge.out_id == db_node.id, Edge.label == 'No')
        edge = db.scalars(query).first()
        if edge:
            edge.in_id = node.no_successor_id
        else:
            edge = Edge(out_id=db_node.id, in_id=node.no_successor_id, label='No')
        
        db.add(edge)

    db.commit()
    db.refresh(db_node)
    
    return db_node


def load_workflow(workflow_id: int, db: Session) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()

    loader_opt = selectin_polymorphic(Node, [StartNode, EndNode, MessageNode, ConditionNode])
    query = select(Node).where(Node.workflow_id == workflow_id).options(loader_opt)
    for node in db.scalars(query):
        graph.add_node(node.id, type=node.type, **model_to_dict(node))

    query = select(Edge).join(Edge.out_node).where(Node.workflow_id == workflow_id)
    for edge in db.scalars(query):
        graph.add_edge(edge.out_id, edge.in_id, label=edge.label)
    
    return graph


@app.get('/workflows/{workflow_id}/launch', name='launch_workflow')
def launch_workflow(workflow_id: int, db: Session = Depends(get_session)):
    workflow_graph = load_workflow(workflow_id, db)

    start_nodes = []
    for node in workflow_graph.nodes:
        if workflow_graph.nodes[node]['type'] == 'startnode':
            start_nodes.append(node)
        
    if len(start_nodes) == 0:
        raise HTTPException(status_code=400, detail='No start node')
    if len(start_nodes) > 1:
        raise HTTPException(status_code=400, detail='Multiple start nodes')

    start_node = start_nodes[0]
    successors = list(workflow_graph.successors(start_node))
    if len(successors) != 1:
        raise HTTPException(status_code=400, detail=f'Start node (id: {start_node}) should have exactly one successor node')
    
    prev_node = start_node
    current_node = successors[0]
    next_node = None
    last_message_node = None
    path = [start_node, current_node]

    while workflow_graph.nodes[current_node]['type'] != 'endnode':

        if workflow_graph.nodes[current_node]['type'] == 'messagenode':
            last_message_node = current_node
            successors = list(workflow_graph.successors(current_node))
            if len(successors) != 1:
                raise HTTPException(status_code=400, detail=f'Message node(id: {current_node}) should have exactly one successor node')
            next_node = successors[0]
        
        elif workflow_graph.nodes[current_node]['type'] == 'conditionnode':
            if workflow_graph.nodes[prev_node]['type'] not in ('messagenode', 'conditionnode'):
                raise HTTPException(status_code=400, detail=f'Condition node(id: {current_node}) should have message node or another condition node as its predecessor')
            
            try:
                rule = rule_engine.Rule(workflow_graph.nodes[current_node]['condition'])
            except rule_engine.errors.RuleSyntaxError as e:
                raise HTTPException(status_code=400, detail=f'Condition node(id: {current_node}) {e.message}')
            
            try:
                is_matched = rule.matches(workflow_graph.nodes[last_message_node])
            except rule_engine.errors.SymbolResolutionError as e:
                raise HTTPException(status_code=400, detail=f'Condition node(id: {current_node}) symbol resolution error: {e.message}')
            
            successors = {label: successor for predecessor, successor, label in workflow_graph.edges(data='label') if predecessor == current_node}
            try:
                result = 'Yes' if is_matched else 'No'
                next_node = successors[result]
                workflow_graph.nodes[current_node]['result'] = result
            except KeyError as e:
                raise HTTPException(status_code=400, detail=f'Condition node(id: {current_node}) don\'t have {e} successor')
        
        prev_node = current_node
        current_node = next_node
        path.append(current_node)


    return {'path': [workflow_graph.nodes[node] for node in path]}
