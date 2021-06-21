import json
import jwt
import requests
import boto3
import time
import datetime
import uuid

from json.decoder      import JSONDecodeError
from datetime          import date

from django.views      import View
from django.http       import JsonResponse

from my_settings       import SECRET, ALGORITHM, JWT_DURATION_SEC
from werecord.settings import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
from utils.decorator   import login_required
from users.models      import User, UserType, Batch, Position

class GoogleLoginView(View):
    def get(self, request):
        id_token     = request.headers.get('Authorization', None)

        if not id_token:
            return JsonResponse({'message': 'ID_TOKEN_REQUIRED'}, status=401)

        user_request = requests.get(f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}')
        user_info    = user_request.json()

        if not user_info:
            return JsonResponse({'message': 'INVALID_TOKEN'}, status=401)

        login_user, created = User.objects.get_or_create(
            google_login_id   = user_info['sub'],
        )

        werecord_token = jwt.encode(
                {
                    'user_id'  : login_user.id,
                    'iat'      : int(time.time()),
                    'exp'      : int(time.time()) + JWT_DURATION_SEC
                }, SECRET['secret'],ALGORITHM
        )

        user_info = {
            'user_id'          : login_user.id,
            'user_type'        : login_user.user_type.name if login_user.user_type else "",
            'batch'            : login_user.batch.name if login_user.batch else "",
            "email'"           : user_info.get('email') if user_info.get('email') else "",
            "profile_image_url": user_info.get('picture') if user_info.get('picture') else "",
        }

        return JsonResponse({'user_info' : user_info, 'werecord_token' : werecord_token}, status=200)

class UserInfoView(View):
    s3_client = boto3.client(
        's3',
        aws_access_key_id     = AWS_ACCESS_KEY_ID,
        aws_secret_access_key = AWS_SECRET_ACCESS_KEY
    )

    @login_required
    def get(self, request):

        user = request.user

        data  = {
                "user_id"          : user.id,
                'profile_image_url': user.profile_image_url,
                'name'             : user.name,
                'user_type'        : user.user_type.name,
                'batch'            : user.batch.name,
                'position'         : user.position.name,
                'blog'             : user.blog,
                'github'           : user.github,
                'birthday'         : str(user.birthday)[5:7] + '.' + str(user.birthday)[8:10],
        }
        return JsonResponse({'data':data}, status =201)

    def post(self, request, user_id):
        try:
            data = json.loads(request.POST['info'])
            user  = User.objects.get(id = user_id) 
            
            image = request.FILES.get('image')


            if image is None:
                image_url = user.profile_image_url

            else:
                my_uuid    = str(uuid.uuid4())

                self.s3_client.upload_fileobj(
                    image,
                    "werecord",
                    my_uuid,
                    ExtraArgs={
                        "ContentType": image.content_type
                    }
                )
        
                image_url = "https://werecord.s3.ap-northeast-2.amazonaws.com/" + my_uuid
            print(data.get("birthday"))

            if data.get("birthday"):
                birthday_list = data.get("birthday").split(".")
                birthday      = '2000' + '-' + birthday_list[0] + '-' + birthday_list[1]
        
            else:
                birthday = None

            User.objects.filter(id = user_id).update(
                profile_image_url = image_url,
                name              = data.get('name'),
                user_type         = UserType.objects.get(name = data.get('user_type')),
                batch             = Batch.objects.get(name = data.get("batch")),
                position          = Position.objects.get(name = data.get("position")),
                blog              = data.get("blog"),
                github            = data.get("github"),
                birthday          = birthday,
            )

            user_info = {
                'user_id'   : user.id,
                'user_type' : user.user_type.name,
                'batch'     : user.batch.name
            }

            return JsonResponse({'user_info': user_info, 'message': 'SUCCESS'}, status =201)
            
        except KeyError:
            return JsonResponse({"message": "KEY_ERROR"}, status=400)

class BatchInfomationView(View):
    def post(self, request):
        try:
            data      = json.loads(request.body)
            start_day = time.strptime(data['start_day'], "%Y-%m-%d")
            end_day   = time.strptime(data['end_day'], "%Y-%m-%d")

            if Batch.objects.filter(name=str(data['name'])).exists():
                return JsonResponse({'message': 'ALREADY_EXIT_ERROR'}, status=400)
            
            if not start_day < end_day:
                return JsonResponse({'message': 'RECHECK_DATE_ERROR'}, status=400)

            if not User.objects.filter(name=data['mentor_name'], user_type_id=1).exists():
                return JsonResponse({'message': 'RECHECK_MENTOR_NAME_ERROR'}, status=400)
            
            Batch.objects.create(id=int(data['name']), name=str(data['name']), 
                                start_day=data['start_day'], end_day=data['end_day'],
                                mentor_name=data['mentor_name'])

            return JsonResponse({'message': 'SUCCESS'}, status=201)
        
        except json.JSONDecodeError:
            return JsonResponse({'message': 'JSON_DECODE_ERROR'}, status=400)

        except ValueError:
            return JsonResponse({'message': 'DATE_FORM_ERROR'}, status=400)

    def patch(self, request):
        try:
            data      = json.loads(request.body)
            start_day = time.strptime(data['start_day'], "%Y-%m-%d")
            end_day   = time.strptime(data['end_day'], "%Y-%m-%d")

            if not start_day < end_day:
                return JsonResponse({'message': 'RECHECK_DATE_ERROR'}, status=400)

            if not User.objects.filter(name=data['mentor_name'], user_type_id=1).exists():
                return JsonResponse({'message': 'RECHECK_MENTOR_NAME_ERROR'}, status=400)

            batch             = Batch.objects.get(id=data['batch_id'])
            batch.start_day   = data['start_day'] if data['start_day'] else batch.start_day
            batch.end_day     = data['end_day'] if data['end_day'] else batch.end_day
            batch.mentor_name = data['mentor_name'] if data['mentor_name'] else batch.mentor_name
            batch.save()

            return JsonResponse({'message': 'SUCCESS'}, status=201)

        except json.JSONDecodeError:
            return JsonResponse({'message': 'JSON_DECODE_ERROR'}, status=400)

        except ValueError:
            return JsonResponse({'message': 'DATE_FORM_ERROR'}, status=400)

    def delete(self, request):
        data = json.loads(request.body)
        Batch.objects.get(id=data['batch_id']).delete()

        return JsonResponse({'message': 'SUCCESS'}, status=204)

class MentorPageView(View):
    @login_required
    def get(self, request):
        user    = request.user
        batches = Batch.objects.all().order_by('-name')
        
        if not user.user_type.id == 1:
            return JsonResponse({'message': 'UNAUTHORIZED_USER_ERROR'}, status = 400)

        now       = datetime.datetime.now()
        time_gap  = datetime.timedelta(seconds=32406)
        now_korea = now + time_gap
        
        total_results = []

        for batch in batches:
            on_user_number   = 0
            user_total_times = []
            users            = User.objects.filter(batch_id=batch.id)

            for user in users:
                user_total_times.append(user.total_time)
                if not user.record_set.last():
                    on_user_number += 0
                elif now_korea.date() == user.record_set.last().start_at.date() and not user.record_set.last().end_at:
                    on_user_number += 1
                else:
                    on_user_number += 0

            result = {
                        'batch_id'                : batch.id,
                        'batch_name'              : batch.name,
                        'batch_start_day'         : batch.start_day,
                        'batch_end_day'           : batch.end_day,
                        'batch_total_time'        : sum(user_total_times),
                        'wecode_d_day'            : (now_korea.date()-batch.start_day).days,
                        'batch_on_user_number'    : on_user_number,
                        'batch_total_user_number' : len(User.objects.filter(batch_id=batch.id))
            }
            
            total_results.append(result)
        
        return JsonResponse({'result': total_results}, status = 200)
    
class StudentPageView(View):
    @login_required
    def get(self, request):
        user = request.user

        if not user.user_type.id == 2:
            return JsonResponse({'message': 'UNAUTHORIZED_USER_ERROR'}, status = 400)

        user      = User.objects.select_related('batch').prefetch_related('record_set').get(id=user.id)
        records   = user.record_set.filter(user_id=user.id)
        now       = datetime.datetime.now()
        time_gap  = datetime.timedelta(seconds=32406)
        now_korea = now + time_gap

        start_sum   = 0
        start_count = 0
        end_sum     = 0
        end_count   = 0

        for record in records:
            standard_time     = record.start_at.replace(hour=0, minute=0, second=0, microsecond=0)

            if record.start_at:
                total         = (record.start_at-standard_time).total_seconds()
                start_sum    += total
                start_count  += 1
            if record.end_at:
                total         = (record.end_at-standard_time).total_seconds()
                end_sum      += total
                end_count    += 1

        today          = now_korea.isocalendar()
        week_start_day = date.fromisocalendar(today.year, today.week, 1)
        week_end_day   = week_start_day + datetime.timedelta(days=6)
        week_records   = records.filter(end_at__date__range=[week_start_day, week_end_day])

        weekly_records     = {f'{record.end_at.weekday()}': record.oneday_time for record in week_records}
        full_weekly_record = {week_number : weekly_records[str(week_number)] \
                                if str(week_number) in weekly_records.keys() else 0 for week_number in range(5)}
                    
        total_accumulate_record_result = []
        oneday_time_sum = 0
        for record in records:
            if record.end_at:
                oneday_time_sum += record.oneday_time
                total_accumulate_record_result.append(oneday_time_sum)

        result = {
                    'user_information' : {
                                'user_id'                : user.id,
                                'user_name'              : user.name,
                                'user_profile_image_url' : user.profile_image_url,
                                'user_total_time'        : user.total_time
                    },
                    'record_information' : {
                                'weekly_record'            : full_weekly_record,
                                'total_accumulate_records' : total_accumulate_record_result,
                                'average_start_time'       : str(datetime.timedelta(seconds=start_sum/start_count)),
                                'average_end_time'         : str(datetime.timedelta(seconds=end_sum/end_count)),
                                'wecode_d_day'             : (now_korea.date()-user.batch.start_day).days

                    }
        }

        return JsonResponse({'result': result}, status = 200)
        
class BatchPageView(View):
    @login_required
    def get(self, request, batch_id):
        user = request.user

        if user.user_type_id == 2 and not user.batch.id == batch_id:
            return JsonResponse({'message': 'NOT_YOUR_BATCH_ERROR'}, status = 400)

        my_batch        = Batch.objects.get(id=batch_id)
        my_batch_users  = User.objects.filter(batch_id=my_batch.id)
        my_batch_mentor = User.objects.get(name=my_batch.mentor_name, user_type_id=1)
        now             = datetime.datetime.now()
        time_gap        = datetime.timedelta(seconds=32406)
        now_korea       = now + time_gap

        all_batches       = Batch.objects.all()
        batch_total_times = []
        for batch in all_batches:
            batch_users = User.objects.filter(batch_id=batch.id)
            batch_total_times.append(sum([user.total_time for user in batch_users]))
        winner_total_time = max(batch_total_times)

        GOST_RANKING = 3

        today               = now_korea.isocalendar()
        last_week_start_day = date.fromisocalendar(today.year, today.week-1, 1)
        last_week_end_day   = last_week_start_day + datetime.timedelta(days=6)

        compare_times = []
        for user in my_batch_users:
            records              = user.record_set.filter(end_at__date__range=[last_week_start_day, last_week_end_day])
            last_week_total_time = 0
            for record in records:
                last_week_total_time += record.oneday_time
            compare_times.append(last_week_total_time)
        
        ranking_results = []
        if len(compare_times) < GOST_RANKING:
            ranking_times = sorted(compare_times, reverse=True)
        else:
            ranking_times = sorted(compare_times, reverse=True)[:GOST_RANKING]

        for ranking_time in ranking_times:
            user_informaion = {}
            index_number = compare_times.index(ranking_time)
            user_informaion['user_id']                   = my_batch_users[index_number].id
            user_informaion['user_name']                 = my_batch_users[index_number].name
            user_informaion['user_profile_image_url']    = my_batch_users[index_number].profile_image_url
            user_informaion['user_last_week_total_time'] = ranking_time
            ranking_results.append(user_informaion)
        
        result = {
                    'winner_batch_information' : {
                                'winner_batch_name'       : all_batches[batch_total_times.index(winner_total_time)].name,
                                'winner_batch_total_time' : winner_total_time
                    },
                    'my_batch_information' : {
                                'batch_id'         : my_batch.id,
                                'batch_name'       : my_batch.name,
                                'batch_total_time' : sum([user.total_time for user in my_batch_users]),
                                'ghost_ranking'    : ranking_results,
                                'peers' : [
                                        {
                                            'batch_id'               : Batch.objects.get(id=batch_id).id,
                                            'batch_name'             : Batch.objects.get(id=batch_id).name,
                                            'peer_id'                : user.id,
                                            'peer_name'              : user.name,
                                            'peer_profile_image_url' : user.profile_image_url,
                                            'peer_position'          : user.position.name,
                                            'peer_email'             : user.email,
                                            'peer_blog'              : user.blog if user.blog else None,
                                            'peer_github'            : user.github if user.github else None,
                                            'peer_birthday'          : user.birthday if user.birthday else None,
                                            'peer_status'            : False if not user.record_set.last() \
                                                else True if now_korea.date() == user.record_set.last().start_at.date() \
                                                and not user.record_set.last().end_at else False,
                                        } for user in my_batch_users
                                ],
                                'mentor' : 
                                        {
                                            'mentor_id'                : my_batch_mentor.id,
                                            'mentor_name'              : my_batch_mentor.name,
                                            'mentor_profile_image_url' : my_batch_mentor.profile_image_url,
                                            'mentor_position'          : my_batch_mentor.position.name,
                                            'mentor_email'             : my_batch_mentor.email,
                                            'mentor_blog'              : my_batch_mentor.blog \
                                                                        if my_batch_mentor.blog else None,
                                            'mentor_github'            : my_batch_mentor.github \
                                                                        if my_batch_mentor.github else None,
                                            'mentor_birthday'          : my_batch_mentor.birthday \
                                                                        if my_batch_mentor.birthday else None
                                        }
                    }
        }
        
        return JsonResponse({'result': result}, status = 200)
