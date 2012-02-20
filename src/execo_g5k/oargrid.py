# Copyright 2009-2012 INRIA Rhone-Alpes, Service Experimentation et
# Developpement
#
# This file is part of Execo.
#
# Execo is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Execo is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Execo.  If not, see <http://www.gnu.org/licenses/>

from config import g5k_configuration
from execo.host import Host
from execo.process import Process, SshProcess
from execo.time_utils import get_unixts, sleep
from oar import format_oar_date, format_oar_duration, _date_in_range, \
    oar_date_to_unixts, oar_duration_to_seconds
from utils import local_site, _get_frontend_connexion_params
import os
import re

def oargridsub(job_specs, reservation_date = None,
               walltime = None, job_type = None,
               queue = None, directory = None,
               additional_options = None,
               frontend_connexion_params = None,
               timeout = False):
    """Submit oargrid jobs.

    :param job_specs: iterable of tuples (OarSubmission,
      clusteralias). Reservation date, walltime, queue, directory,
      project, additional_options, command of the OarSubmission are
      ignored.

    :param reservation_date: grid job reservation date. Default: now.

    :param walltime: grid job walltime.

    :param job_type: type of job for all clusters: deploy, besteffort,
      cosystem, checkpoint, timesharing.

    :param queue: oar queue to use.

    :param directory: directory where the reservation will be
      launched.

    :param additional_options: passed directly to oargridsub on the
      command line.

    :param frontend_connexion_params: connexion params for connecting
      to sites' frontends if needed. Values override those in
      `execo_g5k.config.default_frontend_connexion_params`.

    :param timeout: timeout for retrieving. Default is False, which
      means use
      ``execo_g5k.config.g5k_configuration['default_timeout']``. None
      means no timeout.

    Returns a tuple (oargrid_job_id, ssh_key), or (None, None) if
    error.
    """
    if timeout == False:
        timeout = g5k_configuration['default_timeout']
    oargridsub_cmdline = 'oargridsub'
    if additional_options != None:
        oargridsub_cmdline += ' %s' % (additional_options,)
    oargridsub_cmdline += ' -v'
    if reservation_date:
        oargridsub_cmdline += ' -s "%s" ' % (format_oar_date(reservation_date),)
    if os.environ.has_key('OAR_JOB_KEY_FILE'):
        oargridsub_cmdline += ' -i %s' % (os.environ['OAR_JOB_KEY_FILE'],)
    if queue != None:
        oargridsub_cmdline += '-q "%s" ' % (queue,)
    if job_type != None:
        oargridsub_cmdline += '-t "%s" ' % (job_type,)
    if walltime != None:
        oargridsub_cmdline += '-w "%s" ' % (format_oar_duration(walltime),)
    if directory != None:
        oargridsub_cmdline += '-d "%s" ' % (directory,)
    firstclusteralias = True
    for (spec, clusteralias) in job_specs:
        if firstclusteralias:
            firstclusteralias = False
        else:
            oargridsub_cmdline += ','
            oargridsub_cmdline += '%s:rdef="%s"' % (clusteralias, spec.resources)
        if spec.job_type != None:
            oargridsub_cmdline += ':type="%s"' % (spec.job_type,)
        if spec.sql_properties != None:
            oargridsub_cmdline += ':prop="%s"' % (spec.sql_properties,)
        if spec.name != None:
            oargridsub_cmdline += ':name="%s"' % (spec.name,)
    if g5k_configuration['no_ssh_for_local_frontend'] == True:
        process = Process(oargridsub_cmdline,
                          timeout = timeout,
                          pty = True)
    else:
        process = SshProcess(Host(local_site),
                             oargridsub_cmdline,
                             connexion_params = _get_frontend_connexion_params(frontend_connexion_params),
                             timeout = timeout,
                             pty = True)
    process.run()
    job_id = None
    ssh_key = None
    if process.ok():
        mo = re.search("^\[OAR_GRIDSUB\] Grid reservation id = (\d+)\s*$", process.stdout(), re.MULTILINE)
        if mo != None:
            job_id = int(mo.group(1))
        mo = re.search("^\[OAR_GRIDSUB\] SSH KEY : (.*)\s*$", process.stdout(), re.MULTILINE)
        if mo != None:
            ssh_key = mo.group(1)
    if job_id != None:
        return (job_id, ssh_key)
    else:
        return (None, None)

def oargriddel(job_ids, frontend_connexion_params = None, timeout = False):
    """Delete oargrid jobs.

    Ignores any error, so you can delete inexistant jobs, already
    deleted jobs, or jobs that you don't own. Those deletions will be
    ignored.

    :param job_ids: iterable of oar grid job ids.

    :param frontend_connexion_params: connexion params for connecting
      to sites' frontends if needed. Values override those in
      `execo_g5k.config.default_frontend_connexion_params`.

    :param timeout: timeout for retrieving. Default is False, which
      means use ``g5k_configuration['default_timeout']``. None means no
      timeout.
    """
    if timeout == False:
        timeout = g5k_configuration['default_timeout']
    processes = []
    for job_id in job_ids:
        oargriddel_cmdline = "oargriddel %i" % (job_id,)
        if g5k_configuration['no_ssh_for_local_frontend'] == True:
            processes.append(Process(oargriddel_cmdline,
                                     timeout = timeout,
                                     log_exit_code = False,
                                     pty = True))
        else:
            processes.append(SshProcess(Host(local_site),
                                        oargriddel_cmdline,
                                        connexion_params = _get_frontend_connexion_params(frontend_connexion_params),
                                        timeout = timeout,
                                        log_exit_code = False,
                                        pty = True))
    for process in processes: process.start()
    for process in processes: process.wait()

def get_current_oargrid_jobs(start_between = None,
                             end_between = None,
                             frontend_connexion_params = None,
                             timeout = False):
    """Return a list of current active oargrid job ids.

    :param start_between: a tuple (low, high) of endpoints. Filters
      and returns only jobs whose start date is in between these
      endpoints.
        
    :param end_between: a tuple (low, high) of endpoints. Filters and
      returns only jobs whose end date is in between these endpoints.
        
    :param frontend_connexion_params: connexion params for connecting
      to sites' frontends if needed. Values override those in
      `execo_g5k.config.default_frontend_connexion_params`.

    :param timeout: timeout for retrieving. Default is False, which
      means use
      ``execo_g5k.config.g5k_configuration['default_timeout']``. None
      means no timeout.
    """
    if timeout == False:
        timeout = g5k_configuration['default_timeout']
    if start_between: start_between = [ get_unixts(t) for t in start_between ]
    if end_between: end_between = [ get_unixts(t) for t in end_between ]
    cmd = "oargridstat"
    if g5k_configuration['no_ssh_for_local_frontend'] == True:
        process = Process(cmd,
                          timeout = timeout,
                          pty = True).run()
    else:
        process = SshProcess(Host(local_site),
                             cmd,
                             connexion_params = _get_frontend_connexion_params(frontend_connexion_params),
                             timeout = timeout,
                             pty = True).run()
    if process.ok():
        jobs = re.findall("Reservation # (\d+):", process.stdout(), re.MULTILINE)
        oargrid_job_ids = [ int(j) for j in jobs ]
        if start_between or end_between:
            filtered_job_ids = []
            for job in oargrid_job_ids:
                info = get_oargrid_job_info(job, timeout)
                if (_date_in_range(info['start_date'], start_between)
                    and _date_in_range(info['start_date'] + info['walltime'], end_between)):
                    filtered_job_ids.append(job)
            oargrid_job_ids = filtered_job_ids
        return oargrid_job_ids
    raise Exception, "error, list of current oargrid jobs: %s" % (process,)

def get_oargrid_job_info(oargrid_job_id = None, frontend_connexion_params = None, timeout = False):
    """Return a dict with informations about an oargrid job.

    :param oargrid_job_id: the oargrid job id.

    :param frontend_connexion_params: connexion params for connecting
      to sites' frontends if needed. Values override those in
      `execo_g5k.config.default_frontend_connexion_params`.

    :param timeout: timeout for retrieving. Default is False, which
      means use
      ``execo_g5k.config.g5k_configuration['default_timeout']``. None
      means no timeout.

    Hash returned contains these keys:

    - ``start_date``: unix timestamp of job's start date

    - ``walltime``: job's walltime in seconds
    """
    if timeout == False:
        timeout = g5k_configuration['default_timeout']
    cmd = "oargridstat %i" % oargrid_job_id
    if g5k_configuration['no_ssh_for_local_frontend'] == True:
        process = Process(cmd,
                          timeout = timeout,
                          pty = True)
    else:
        process = SshProcess(Host(local_site),
                             cmd,
                             connexion_params = _get_frontend_connexion_params(frontend_connexion_params),
                             timeout = timeout,
                             pty = True)
    process.run()
    if process.ok():
        job_info = dict()
        start_date_result = re.search("start date : (\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d)", process.stdout(), re.MULTILINE)
        if start_date_result:
            start_date = oar_date_to_unixts(start_date_result.group(1))
            job_info['start_date'] = start_date
        walltime_result = re.search("walltime : (\d+:\d?\d:\d?\d)", process.stdout(), re.MULTILINE)
        if walltime_result:
            walltime = oar_duration_to_seconds(walltime_result.group(1))
            job_info['walltime'] = walltime
        return job_info
    raise Exception, "error retrieving info for oargrid job %i: %s" % (oargrid_job_id, process)

def wait_oargrid_job_start(oargrid_job_id = None, frontend_connexion_params = None, timeout = False):
    """Sleep until an oargrid job's start time.

    :param oargrid_job_id: the oargrid job id.

    :param frontend_connexion_params: connexion params for connecting
      to sites' frontends if needed. Values override those in
      `execo_g5k.config.default_frontend_connexion_params`.

    :param timeout: timeout for retrieving. Default is False, which
      means use
      ``execo_g5k.config.g5k_configuration['default_timeout']``. None
      means no timeout.
    """
    sleep(until = get_oargrid_job_info(oargrid_job_id, frontend_connexion_params, timeout)['start_date'])

def get_oargrid_job_nodes(oargrid_job_id, frontend_connexion_params = None, timeout = False):
    """Return an iterable of `execo.host.Host` containing the hosts of an oargrid job.

    :param oargrid_job_id: the oargrid job id.

    :param frontend_connexion_params: connexion params for connecting
      to sites' frontends if needed. Values override those in
      `execo_g5k.config.default_frontend_connexion_params`.

    :param timeout: timeout for retrieving. Default is False, which
      means use
      ``execo_g5k.config.g5k_configuration['default_timeout']``. None
      means no timeout.
    """
    if timeout == False:
        timeout = g5k_configuration['default_timeout']
    cmd = "oargridstat -wl %i" % oargrid_job_id
    if g5k_configuration['no_ssh_for_local_frontend'] == True:
        process = Process(cmd,
                          timeout = timeout,
                          pty = True)
    else:
        process = SshProcess(Host(local_site),
                             cmd,
                             connexion_params = _get_frontend_connexion_params(frontend_connexion_params),
                             timeout = timeout,
                             pty = True)
    process.run()
    if process.ok():
        host_addresses = re.findall("(\S+)", process.stdout(), re.MULTILINE)
        return list(set([ Host(host_address) for host_address in host_addresses ]))
    raise Exception, "error retrieving nodes list for oargrid job %i: %s" % (oargrid_job_id, process)
