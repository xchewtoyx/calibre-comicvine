# Copyright (c) 2013 Martin Lenders
#
# Permission is hereby granted, free of charge, to any person obtaining 
# a copy of this software and associated documentation files (the 
# "Software"), to deal in the Software without restriction, including 
# without limitation the rights to use, copy, modify, merge, publish, 
# distribute, sublicense, and/or sell copies of the Software, and to 
# permit persons to whom the Software is furnished to do so, subject to 
# the following conditions:
#
# The above copyright notice and this permission notice shall be 
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, 
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF 
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND 
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS 
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN 
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN 
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE 
# SOFTWARE.

import urllib.request, urllib.error, urllib.parse
from urllib.parse import urlencode
try:
    import simplejson as json
except ImportError:
    import json
import sys, re
import datetime, logging
import dateutil.parser
from . import error
import collections
try:
    collectionsAbc = collections.abc
except AttributeError:
    collectionsAbc = collections

from calibre import random_user_agent

_API_URL = "https://www.comicvine.com/api/"

_cached_resources = {}
_api_hooks = {}

api_key = ""

def str_to_datetime(value):
    try:
        return dateutil.parser.parse(value)
    except ValueError:
        return value

def hook_register(hook_name, callback):
    if callable(callback):
        _api_hooks[hook_name] = callback
    else:
        raise error.IllegalArquementException(
            "Hook callbacks must be callable"
        )

def hook_run(hook_name, *args, **kwargs):
    if callable(_api_hooks.get(hook_name)):
        _api_hooks[hook_name](*args, **kwargs)

class AttributeDefinition(object):
    def __init__(self, target, start_type = None):
        def _to_int(value):
            try:
                new_value = value.replace(',','')
                return int(new_value)
            except ValueError:
                return value

        self._start_type = start_type
        if target == datetime.datetime or target == 'datetime':
            self._target = str_to_datetime
            self._target_name = 'datetime'
        elif target == int or target == 'int':
            self._target = _to_int
            self._target_name = 'int'
        elif callable(target):
            if not isinstance(start_type, type) and \
                not (isinstance(start_type, collectionsAbc.Iterable) and
                     all(isinstance(t, type) for t in start_type)):
                raise error.IllegalArquementException(
                        "A start type needs to be defined"
                    )
            self._target = target
            self._target_name = 'callable'
        elif target == 'keep':
            self._target = lambda value: value
            self._target_name = 'keep'
        else:
            self._target = None
            self._target_name = target

    def convert(self, value):
        if self._target_name == 'callable' and \
                isinstance(value, self._start_type):
            return self._target(value)
        elif self._target != None:
            if value == None:
                pass
            elif isinstance(value, str):
                return self._target(value)
        else:
            target = getattr(sys.modules[__name__], self._target_name)
            if issubclass(target, _SingularResource):
                if isinstance(value, dict):
                    value = target(do_not_download=True, **value)
                else:
                    return value
            elif issubclass(target, _ListResource):
                if isinstance(value, list):
                    value = target(value)
                elif value == None:
                    value = target([])
                else:
                    return value
            else:
                raise error.NotConvertableError(
                        "Error in convertion '"+str(value)+"' => "+\
                        self._target_name
                    )
        return value

class _Resource(object):
    class _Response:
        def __init__(
                self,
                error,
                limit,
                offset,
                number_of_page_results,
                number_of_total_results,
                status_code,
                results,
                version = None
            ):
            self.error = error
            self.limit = limit
            self.offset = offset
            self.number_of_page_results = number_of_page_results
            self.number_of_total_results = number_of_total_results
            self.status_code = status_code
            if results != None:
                self.results = results
            else:
                self.results = []

    def __init__(self, *args, **kwargs):
        raise NotImplemented()

    def _request_object(self, baseurl, **params):
        raise NotImplemented()

    @classmethod
    def _ensure_resource_url(type):
        if not '_resource_url' in type.__dict__:
            resource_type = Types.snakify_type_name(type)
            type._resource_url = _API_URL + resource_type + "/"

    @classmethod
    def _request(type, baseurl, **params):
        if 'api_key' not in params:
            if len(api_key) == 0:
                raise error.InvalidAPIKeyError(
                        "Invalid API Key"
                    )
            params['api_key'] = api_key
        if 'field_list' in params and params['field_list'] != None:
            if not isinstance(params['field_list'], str):
                field_list = ""
                try:
                    for field_name in params['field_list']:
                        field_list += str(field_name)+","
                except TypeError as e:
                    raise error.IllegalArquementException(
                            "'field_list' must be iterable"
                        )
                params['field_list'] = field_list
            if re.search(
                    "([a-z_]*,)*id(,[a-z_]*)*", params['field_list']
                ) == None:
                params['field_list'] = "id," + params['field_list']
        timeout = None
        if 'timeout' in params:
            if timeout != None:
                timeout = int(params['timeout'])
            del params['timeout']
        params['format'] = 'json'
        params = urlencode(params)
        url = baseurl+"?"+params
        hook_run('pre_request_hook')
        logging.getLogger(__name__).debug("Calling "+url)
        urlHeaders = {'User-Agent': random_user_agent()}
        logging.getLogger(__name__).debug("Agent "+urlHeaders["User-Agent"])
        urlRequest = urllib.request.Request(url, headers=urlHeaders)

        if timeout == None:
            response_raw = json.loads(urllib.request.urlopen(urlRequest).read())
        else:
            response_raw = json.loads(urllib.request.urlopen(
                    urlRequest, 
                    timeout=timeout
                ).read())
        response = type._Response(**response_raw)
        if response.status_code != 1:
            raise error.EXCEPTION_MAPPING.get(
                    response.status_code,
                    error.UnknownStatusError
                )(response.error)
        if 'aliases' in response.results and \
                isinstance(response.results['aliases'], str):
            response.results['aliases'] = response.results[
                    'aliases'
                ].split('\n')
        return response

class _SingularResource(_Resource):
    def __new__(
            type,
            id,
            all = False,
            field_list = [],
            do_not_download = False,
            **kwargs
        ):
        resource_type = kwargs.get(
                'resource_type',
                type
            )
        try:
            type_id = Types()[resource_type]['id']
        except KeyError:
            return error.InvalidResourceError(
                    resource_type
                )
        type._ensure_resource_url()
        key = "{0:d}-{1:d}".format(type_id, id)
        obj = _cached_resources.get(key)
        if obj == None:
            obj = object.__new__(type)
            _cached_resources[key] = obj
        return obj

    def __init__(
            self,
            id,
            all = False,
            field_list = [],
            do_not_download = False,
            **kwargs
        ):
        if '_ready' not in self.__dict__:
            self._ready = True
            try:
                type_id = Types()[type(self)]['id']
            except KeyError:
                raise error.InvalidResourceError(
                        "Resource type '{0!s}' does not exist.".format(
                                type(self)
                            )
                    )
            self._detail_url = type(self)._resource_url + \
                    "{0:d}-{1:d}/".format(type_id, id)
            self._fields = {'id': id}
            if not do_not_download:
                if all:
                    self._fields.update(self._request_object().results)
                else:
                    self._fields.update(self._request_object(
                            field_list
                        ).results)
            if 'field_list' in kwargs:
                del kwargs['field_list']
            self._fields.update(kwargs)
        elif 'field_list' in kwargs:
            if not all or not do_not_download:
                self._fields.update(self._request_object(
                        kwargs['field_list']
                    ).results)
        if all and not do_not_download:
            if 'timeout' in kwargs:
                self._fields.update(self._request_object(
                        timeout=kwargs['timeout']
                    ).results)

    def _request_object(self, field_list = None, timeout = None):
        if field_list == None:
            return type(self)._request(
                    self._detail_url,
                    timeout=timeout
                )
        else:
            return type(self)._request(
                    self._detail_url,
                    field_list=field_list,
                    timeout=timeout
                )

    def __getattribute__(self, name):
        def _object_attribute(name):
            return object.__getattribute__(self, name)

        def _parse_attribute(name):
            fields = _object_attribute('_fields')
            value = _object_attribute('_fields')[name]
            if name in [x for x in type(self).__dict__ if not x.startswith('_')]:
                definition = type(self).__dict__[name]
                fields[name] = definition.convert(value)
            return fields[name]

        name = _object_attribute('_fix_api_error')(name)
        try:
            if name not in [
                    '__class__', 
                    '__dict__', 
                    '__member__', 
                    '__methods__', 
                    '_request_object'
                ] and name not in self.__dict__:
                if name in _object_attribute('_fields'):
                    return _parse_attribute(name)
                else:
                    self._fields.update(
                            _object_attribute('_request_object')(
                                    [name]
                                ).results
                        )
                    return _parse_attribute(name)
        except KeyError:
            pass
        return _object_attribute(name)

    def _fix_api_error(self, name):
        return name

    def __str__(self):
        if 'name' in self._fields:
            return str(self.name.encode(
                    'ascii',
                    'backslashreplace'
                )) + " ["+str(self.id)+"]"
        else:
            return "["+str(self.id)+"]"

    def __unicode__(self):
        if 'name' in self._fields:
            return str(self.name.encode(
                    'ascii',
                    'backslashreplace'
                )) + " ["+str(self.id)+"]"
        else:
            return "["+str(self.id)+"]"

    def __repr__(self):
        return "<"+str(type(self).__name__)+": "+str(self)\
                +">"

class _ListResource(_Resource):
    def _request_object(self, **params):
        type(self)._ensure_resource_url()
        if isinstance(self, Search):
            if 'offset' in params:
                limit = params['limit'] or self._limit
                params['page'] = params['offset']/params['limit'] + 1
                del params['offset']
            elif 'page' not in params:
                params['page'] = 1
        return type(self)._request(type(self)._resource_url, **params)

    def __init__(self, init_list = None, **kwargs):
        if init_list != None:
            if len(kwargs) > 0:
                raise TypeError(
                        "If 'init_list' is given it is the only "+
                        "allowed argument"
                    )
            self._results = init_list
            self._total = len(init_list)
            self._limit = len(init_list)
        else:
            response = self._request_object(**kwargs)
            self._results = response.offset*[None] + response.results
            self._total = response.number_of_total_results
            self._limit = response.limit
            if 'limit' in kwargs:
                del kwargs['limit']
            if 'offset' in kwargs:
                del kwargs['offset']
            self._args = kwargs

    def __len__(self):
        return self._total

    def __getitem__(self, index):
        if isinstance(index, slice):
            start = index.start or 0
            stop = index.stop or self._total
            step = index.step or 1
        else:
            start = index
            stop = index+1
            step = 1
        if start < 0 or start >= self._total or \
                stop > self._total:
            raise IndexError('Index out of range')
        if len(self._results) < stop or \
                None in self._results[start:stop:step]:
            for i in range(start, stop, 100):
                response = self._request_object(
                        limit=self._limit,
                        offset=i,
                        **self._args
                    )
                if response.number_of_page_results != len(response.results):
                    logging.getLogger(__name__).warning("number of page results wrong (%d != %d) ",
                            response.number_of_page_results, len(response.results))
                if isinstance(self, Search):
                    end_result = response.offset + response.number_of_page_results
                    if len(self._results) < end_result:
                        self._results.extend(
                            [None] * (end_result - len(self._results)))
                    for j in range(response.offset, 
                                   response.offset+len(response.results)):
                            self._results[j] = response.results[j-response.offset]
                else:
                    for j in range(
                            len(self._results),
                            i+response.number_of_page_results
                        ):
                        self._results.append(None)
                    for j in range(i, i+response.number_of_page_results):
                        self._results[j] = response.results[j-i]         
        if isinstance(self._results[index], list):
            if not isinstance(index, slice) and len(self._results[index]) == 0:
                self._results[index] = None
                return None
            for i in range(start, stop, step):
                if isinstance(self._results[i], dict):
                    self._parse_result(i)
                elif isinstance(self._results[i], list) and \
                        len(self._results[i]) == 0:
                    self._results[i] = None
        elif isinstance(self._results[index], dict):
            self._parse_result(index)
        return self._results[index]

    def __iter__(self):
        for index in range(self._total):
            yield self[index]

    def __str__(self):
        return str(str(self))

    def __unicode__(self):
        if len(self) == 0:
            return "[]"
        string = "["
        for element in self:
            string += str(element)+", "
        string = string[:-2]+"]"
        return string

    def __repr__(self):
        if len(self) == 0:
            return str(type(self).__name__)+"[]"
        string = str(type(self).__name__)+"["
        for element in self:
            string += repr(element)+","
        string = string[:-1]+"]"
        return string

    def _parse_result(self, index):
        if type(self) != Types:
            type_dict = Types()
            if isinstance(self, Search):
                self._results[index] = type_dict[
                        self._results[index]['resource_type']
                    ]['singular_resource_class'](
                            do_not_download=True,
                            **self._results[index]
                        )
            else:
                self._results[index] = type_dict[type(self)][
                        'singular_resource_class'
                    ](do_not_download=True, **self._results[index])

class _SortableListResource(_ListResource):
    def __init__(self, init_list = None, sort = None, **kwargs):
        if sort != None:
            if isinstance(sort, str):
                if ':' not in sort:
                    sort += ":asc"
            else:
                try:
                    sort = str(sort[0])+":"+str(sort[1])
                except KeyError:
                    if 'field' not in sort:
                        raise error.IllegalArquementException(
                                "Argument 'sort' must contain item 'field'"
                            )
                    if 'direction' in sort:
                        sort = sort['field']+":"+str(sort['direction'])
                    else:
                        sort = sort['field']+":asc"
            kwargs['sort'] = sort
        super(_SortableListResource, self).__init__(init_list, **kwargs)

    @classmethod
    def search(type, query, **kwargs):
        if 'resources' in kwargs:
            del kwargs['resources']
        types = Types()
        resource_type = types[
                Types.snakify_type_name(type)
            ]['detail_resource_name']
        return Search(query=query, resources=resource_type, **kwargs)

class Character(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    birth = AttributeDefinition(datetime.datetime)
    character_enemies = AttributeDefinition('Characters')
    character_friends = AttributeDefinition('Characters')
    count_of_issue_appearances = AttributeDefinition('keep')
    creators = AttributeDefinition('People')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appeared_in_issue = AttributeDefinition('Issue')
    gender = AttributeDefinition(
            lambda value:   '\u2642' if value == 1 else
                            '\u2640' if value == 2 else '\u26a7',
            int
        )
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issue_credits = AttributeDefinition('Issues')
    issues_died_in = AttributeDefinition('Issues')
    movies = AttributeDefinition('Movies')
    name = AttributeDefinition('keep')
    origin = AttributeDefinition('Origin')
    powers = AttributeDefinition('Powers')
    publisher = AttributeDefinition('Publisher')
    real_name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    story_arc_credits = AttributeDefinition('StoryArcs')
    team_enemies = AttributeDefinition('Teams')
    team_friends = AttributeDefinition('Teams')
    teams = AttributeDefinition('Teams')
    volume_credits = AttributeDefinition('Volumes')

class Characters(_SortableListResource):
    pass

class Chat(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    channel_name = AttributeDefinition('keep')
    deck = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    password = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    title = AttributeDefinition('keep')

class Chats(_SortableListResource):
    @classmethod
    def search(type, query, **kwargs):
        return None

class Concept(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    count_of_isssue_appearances = AttributeDefinition('keep')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appeared_in_issue = AttributeDefinition('Issue')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issue_credits = AttributeDefinition('Issues')
    movies = AttributeDefinition('Movies')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    start_year = AttributeDefinition(int)
    volume_credits = AttributeDefinition('Volumes')

    def _fix_api_error(self, name):
        if name == 'count_of_issue_appearances':
            return 'count_of_isssue_appearances'
        return super(Concept, self)._fix_api_error(name)

class Concepts(_SortableListResource):
    pass

class Episode(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    character_credits = AttributeDefinition('Characters')
    characters_died_in = AttributeDefinition('Characters')
    concept_credits = AttributeDefinition('Concepts')
    air_date = AttributeDefinition(datetime.datetime)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appearance_characters = AttributeDefinition('Characters')
    first_appearance_concepts = AttributeDefinition('Concepts')
    first_appearance_locations = AttributeDefinition('Locations')
    first_appearance_objects = AttributeDefinition('Objects')
    first_appearance_storyarcs = AttributeDefinition('StoryArcs')
    first_appearance_teams = AttributeDefinition('Teams')
    has_staff_review = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    episode_number = AttributeDefinition('keep')
    location_credits = AttributeDefinition('Locations')
    name = AttributeDefinition('keep')
    object_credits = AttributeDefinition('Objects')
    person_credits = AttributeDefinition('People')
    site_detail_url = AttributeDefinition('keep')
    story_arc_credits = AttributeDefinition('StoryArcs')
    team_credits = AttributeDefinition('team_credits')
    series = AttributeDefinition('Series')

class Episodes(_SortableListResource):
    pass

class Issue(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    character_credits = AttributeDefinition('Characters')
    character_died_in = AttributeDefinition('Characters')
    concept_credits = AttributeDefinition('Concepts')
    cover_date = AttributeDefinition(datetime.datetime)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appearance_characters = AttributeDefinition('Characters')
    first_appearance_concepts = AttributeDefinition('Concepts')
    first_appearance_locations = AttributeDefinition('Locations')
    first_appearance_objects = AttributeDefinition('Objects')
    first_appearance_storyarcs = AttributeDefinition('StoryArcs')
    first_appearance_teams = AttributeDefinition('Teams')
    has_staff_review = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issue_number = AttributeDefinition(int)
    location_credits = AttributeDefinition('Locations')
    name = AttributeDefinition('keep')
    object_credits = AttributeDefinition('Objects')
    person_credits = AttributeDefinition('People')
    site_detail_url = AttributeDefinition('keep')
    store_date = AttributeDefinition(datetime.datetime)
    story_arc_credits = AttributeDefinition('StoryArcs')
    team_credits = AttributeDefinition('Teams')
    team_disbanded_in = AttributeDefinition('Teams')
    volume = AttributeDefinition('Volume')

    def __unicode__(self):
        string = ""
        if 'name' in self._fields and self._fields['name'] != None:
            string += str(self.name.encode(
                        'ascii',
                        'backslashreplace'
                    ))+" "
            if 'issue_number' in self._fields:
                string += "#"+str(self.issue_number)+" "
        else:
            if 'issue_number' in self._fields:
                string += "#"+str(self.issue_number)+" "
            if 'volume' in self._fields:
                string = str(self.volume.name.encode(
                        'ascii',
                        'backslashreplace'
                    ))+" "+string
        return string + "["+str(self.id)+"]"

    def _fix_api_error(self, name):
        if name == 'characters_died_in':
            return 'character_died_in'
        if name == 'disbanded_teams':
            return 'team_disbanded_in'
        if name == 'teams_disbanded_in':
            return 'team_disbanded_in'
        return super(Issue, self)._fix_api_error(name)

class Issues(_SortableListResource):
    pass

class Location(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    count_of_issue_appearances = AttributeDefinition(int)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appeared_in_issue = AttributeDefinition('Issue')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issue_credits = AttributeDefinition('Issues')
    movies = AttributeDefinition('Movies')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    start_year = AttributeDefinition(int)
    story_arc_credits = AttributeDefinition('StoryArcs')
    volume_credits = AttributeDefinition('Volumes')

class Locations(_SortableListResource):
    pass

class Movie(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    box_office_revenue = AttributeDefinition(int)
    budget = AttributeDefinition(int)
    characters = AttributeDefinition('Characters')
    concepts = AttributeDefinition('Concepts')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    distibutor = AttributeDefinition('keep')
    has_staff_review = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    locations = AttributeDefinition('Locations')
    name = AttributeDefinition('keep')
    producers = AttributeDefinition('People')
    rating = AttributeDefinition('keep')
    release_date = AttributeDefinition(datetime.datetime)
    runtime = AttributeDefinition(
            lambda value:   int(str(value).split(':'))[0] * 60 + \
                            int(str(value).split(':')[1]) \
                                if ':' in str(value) \
                                else int(value),
            str
        )
    site_detail_url = AttributeDefinition('keep')
    studios = AttributeDefinition('keep')
    teams = AttributeDefinition('Teams')
    objects = AttributeDefinition('Objects')
    total_revenue = AttributeDefinition(int)
    writers = AttributeDefinition('People')

    def _fix_api_error(self, name):
        if name == 'things':
            return 'objects'
        return super(Movie, self)._fix_api_error(name)

class Movies(_SortableListResource):
    pass

class Object(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    count_of_issue_appearances = AttributeDefinition(int)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appeared_in_issue = AttributeDefinition('Issue')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issue_credits = AttributeDefinition('Issues')
    movies = AttributeDefinition('Movies')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    start_year = AttributeDefinition(int)
    story_arc_credits = AttributeDefinition('StoryArcs')
    volume_credits = AttributeDefinition('Volumes')

class Objects(_SortableListResource):
    pass

class Origin(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    character_set = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    name = AttributeDefinition('keep')
    profiles = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')

class Origins(_SortableListResource):
    @classmethod
    def search(type, query, **kwargs):
        return None

class Person(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    birth = AttributeDefinition(datetime.datetime)
    count_of_isssue_appearances = AttributeDefinition('keep')
    country = AttributeDefinition('keep')
    created_characters = AttributeDefinition('Characters')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    death = AttributeDefinition(
            lambda value:   str_to_datetime(value.get('date')) if 
                                isinstance(value, dict) else
                            str_to_datetime(value),
            (dict, str)
        )
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    email = AttributeDefinition('keep')
    gender = AttributeDefinition(
            lambda value:   '\u2642' if value == 1 else
                            '\u2640' if value == 2 else '\u26a7',
            int
        )
    hometown = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issues = AttributeDefinition('Issues')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    story_arc_credits = AttributeDefinition('StoryArcs')
    volume_credits = AttributeDefinition('Volumes')
    website = AttributeDefinition('keep')

    def _fix_api_error(self, name):
        if name == 'count_of_issue_appearances':
            return 'count_of_isssue_appearances'
        if name == 'issue_credits':
            return 'issues'
        return super(Person, self)._fix_api_error(name)

class People(_SortableListResource):
    pass

class Power(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    characters = AttributeDefinition('Characters')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    description = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')

class Powers(_SortableListResource):
    @classmethod
    def search(type, query, **kwargs):
        return None

class Promo(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    date_added = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    link = AttributeDefinition('keep')
    name = AttributeDefinition('keep')

class Promos(_SortableListResource):
    @classmethod
    def search(type, query, **kwargs):
        return None

class Publisher(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    characters = AttributeDefinition('Characters')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    location_address = AttributeDefinition('keep')
    location_city = AttributeDefinition('keep')
    location_state = AttributeDefinition('keep')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')
    story_arcs = AttributeDefinition('StoryArcs')
    teams = AttributeDefinition('Teams')
    volumes = AttributeDefinition('Volumes')

class Publishers(_SortableListResource):
    pass

class Search(_ListResource):
    def __init__(self, query, **kwargs):
        super(Search, self).__init__(query=query, **kwargs)

class Series(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    character_credits = AttributeDefinition('Characters')
    count_of_episodes = AttributeDefinition('keep')
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_episode = AttributeDefinition('Episode')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    last_episode = AttributeDefinition('Episode')
    location_credits = AttributeDefinition('Locations')
    name = AttributeDefinition('keep')
    publisher = AttributeDefinition('Publisher')
    site_detail_url = AttributeDefinition('keep')
    start_year = AttributeDefinition('keep')

class SeriesList(_ListResource):
    pass

class StoryArc(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    count_of_isssue_appearances = AttributeDefinition(int)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_appeared_in_issue = AttributeDefinition('Issue')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issues = AttributeDefinition('Issues')
    movies = AttributeDefinition('Movies')
    name = AttributeDefinition('keep')
    publisher = AttributeDefinition('Publisher')
    site_detail_url = AttributeDefinition('keep')

    def _fix_api_error(self, name):
        if name == 'count_of_issue_appearances':
            return 'count_of_isssue_appearances'
        return super(StoryArc, self)._fix_api_error(name)

class StoryArcs(_SortableListResource):
    pass

class Team(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    character_enemies = AttributeDefinition('Characters')
    character_friends = AttributeDefinition('Characters')
    characters = AttributeDefinition('Characters')
    count_of_isssue_appearances = AttributeDefinition(int)
    count_of_team_members = AttributeDefinition(int)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    disbanded_in_issues = AttributeDefinition('Issues')
    first_appeared_in_issue = AttributeDefinition('Issue')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issue_credits = AttributeDefinition('Issues')
    isssues_disbanded_in = AttributeDefinition('Issues')
    movies = AttributeDefinition('Movies')
    name = AttributeDefinition('keep')
    publisher = AttributeDefinition('Publisher')
    site_detail_url = AttributeDefinition('keep')
    story_arc_credits = AttributeDefinition('StoryArcs')
    volume_credits = AttributeDefinition('Volumes')

    def _fix_api_error(self, name):
        if name == 'count_of_issue_appearances':
            return 'count_of_isssue_appearances'
        if name == 'issues_disbanded_in':
            return 'isssues_disbanded_in'
        return super(Team, self)._fix_api_error(name)

class Teams(_SortableListResource):
    pass

class Types(_ListResource):
    def __new__(type):
        if not '_instance' in type.__dict__:
            type._instance = object.__new__(type)
        return type._instance

    def __init__(self):
        if not '_ready' in dir(self):
            super(Types, self).__init__()
            self._mapping = {}
            for type in self:
                type['singular_resource_class'] = getattr(
                        sys.modules[__name__],
                        Types._camilify_type_name(
                                type['detail_resource_name']),
                        UnknownResource
                    )
                self._mapping[type['detail_resource_name']] = type
                self._mapping[type['list_resource_name']] = type
            self._ready = True

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return super(Types, self).__getitem__(key)
        if isinstance(key, type):
            return self._mapping[self.snakify_type_name(key)]
        return self._mapping[key]

    @staticmethod
    def snakify_type_name(type):
        return re.sub(r'([A-Z]+)',r"_\1", type.__name__)[1:].lower()

    @staticmethod
    def _camilify_type_name(string):
        string = string[0].upper() + string[1:].lower()
        camel_string = ""
        next_upper = False
        for c in string:
            if c == "_":
                next_upper = True
                continue
            if next_upper:
                camel_string += c.upper()
                next_upper = False
            else:
                camel_string += c
        return camel_string

class UnknownResource(_Resource):
    pass

class Video(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    deck = AttributeDefinition('keep')
    high_url = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    length_seconds = AttributeDefinition('keep')
    low_url = AttributeDefinition('keep')
    name = AttributeDefinition('keep')
    publish_date = AttributeDefinition(datetime.datetime)
    site_detail_url = AttributeDefinition('keep')
    url = AttributeDefinition('keep')
    user = AttributeDefinition('keep')

class Videos(_SortableListResource):
    pass

class VideoType(_SingularResource):
    api_detail_url = AttributeDefinition('keep')
    deck = AttributeDefinition('keep')
    id = AttributeDefinition('keep')
    name = AttributeDefinition('keep')
    site_detail_url = AttributeDefinition('keep')

class VideoTypes(_SortableListResource):
    @classmethod
    def search(type, query, **kwargs):
        return None

class Volume(_SingularResource):
    aliases = AttributeDefinition('keep')
    api_detail_url = AttributeDefinition('keep')
    characters = AttributeDefinition('Characters')
    concepts = AttributeDefinition('Concepts')
    count_of_issues = AttributeDefinition(int)
    date_added = AttributeDefinition(datetime.datetime)
    date_last_updated = AttributeDefinition(datetime.datetime)
    deck = AttributeDefinition('keep')
    description = AttributeDefinition('keep')
    first_issue = AttributeDefinition('Issue')
    id = AttributeDefinition('keep')
    image = AttributeDefinition('keep')
    issues = AttributeDefinition('Issues')
    last_issue = AttributeDefinition('Issue')
    locations = AttributeDefinition('Locations')
    name = AttributeDefinition('keep')
    objects = AttributeDefinition('Objects')
    people = AttributeDefinition('People')
    publisher = AttributeDefinition('Publisher')
    site_detail_url = AttributeDefinition('keep')
    start_year = AttributeDefinition(int)

    def _fix_api_error(self, name):
        if name == 'character_credits':
            return 'characters'
        if name == 'concept_credits':
            return 'concepts'
        if name == 'location_credits':
            return 'locations'
        if name == 'object_credits':
            return 'objects'
        if name == 'person_credits':
            return 'people'
        return super(Volume, self)._fix_api_error(name)

class Volumes(_SortableListResource):
    pass
